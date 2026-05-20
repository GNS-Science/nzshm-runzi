"""Helpers for routing a runzi invocation through a local Docker container."""

import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich import print as rich_print

load_dotenv()

_ENV_PASSTHROUGH = frozenset(
    [
        'AWS_PROFILE',
        'AWS_REGION',
        'THS_DATASET_AGGR_URI',
    ]
)

# NZSHM22_* env vars that should be forwarded from host to container.
# Image-set path vars (NZSHM22_SCRIPT_WORK_PATH, OPENSHA_*, FATJAR, OQ_*, THS_*)
# are intentionally omitted — the image provides container-side defaults and the
# wrapper mounts host directories at those paths when applicable
# (THS via _resolve_ths, work-path via _resolve_work_path).
_ENV_FORWARDED_NZSHM_VARS: frozenset[str] = frozenset(
    [
        'NZSHM22_TOSHI_API_ENABLED',
        'NZSHM22_TOSHI_API_URL',
        'NZSHM22_TOSHI_API_KEY',
        'NZSHM22_TOSHI_S3_URL',
        'NZSHM22_TOSHI_COGNITO_DOMAIN',
        'NZSHM22_TOSHI_COGNITO_SCIENTIST_CLIENT_ID',
        'NZSHM22_TOSHI_COGNITO_REGION',
        'NZSHM22_TOSHI_M2M_SECRET_ARN',
        'NZSHM22_RUNZI_ECR_DIGEST',
        'NZSHM22_SCRIPT_WORKER_POOL_SIZE',
        'NZSHM22_SCRIPT_JVM_HEAP_START',
        'NZSHM22_BUILD_PLOTS',
        'NZSHM22_REPORT_LEVEL',
        'NZSHM22_HACK_FAULT_MODEL',
        'NZSHM22_S3_REPORT_BUCKET',
        'NZSHM22_S3_UPLOAD_WORKERS',
    ]
)

_TOSHI_HOME_CONTAINER = '/toshi-home'

_DEFAULT_IMAGE = 'runzi-build:latest'
_DEFAULT_DEV_IMAGE = 'runzi-build:dev'
_DEFAULT_ECR_REPO = 'nzshm22/runzi'
_DEFAULT_AWS_ACCOUNT = '461564345538'
_DEFAULT_AWS_REGION = 'us-east-1'

_INPUT_FILES = '/INPUT_FILES'
_AWS_CREDS_CONTAINER = '/aws-credentials'
_WORK_PATH_CONTAINER = '/WORKING'


# ── Pure path helpers ─────────────────────────────────────────────────────────


def find_file_args(args: list[str]) -> list[Path]:
    """Return any args that are existing files on the host."""
    found = []
    for arg in args:
        p = Path(arg)
        if p.is_file():
            found.append(p)
    return found


def common_ancestor(paths: list[Path]) -> Path:
    """Return the deepest directory that contains all paths."""
    if len(paths) == 1:
        return paths[0].parent
    return Path(os.path.commonpath([str(p.parent) for p in paths]))


def rewrite_file_args(args: list[str], file_args: list[Path], ancestor: Path) -> list[str]:
    """Replace host file paths in args with their /INPUT_FILES equivalents."""
    file_map = {str(f): f for f in file_args}
    result = []
    for arg in args:
        if arg in file_map:
            rel = file_map[arg].relative_to(ancestor)
            result.append(f'{_INPUT_FILES}/{rel.as_posix()}')
        else:
            result.append(arg)
    return result


# ── Command assembly ──────────────────────────────────────────────────────────


def build_docker_cmd(
    *,
    inner_args: list[str],
    image: str,
    dev: bool,
    shell: bool,
    aws_credentials: Path,
    ths_hazard: Path | None,
    ths_disagg: Path | None,
    env_vars: dict[str, str],
    input_dir: Path | None = None,
    runzi_source: Path | None = None,
    interactive: bool = False,
    work_path: Path | None = None,
    toshi_home: Path | None = None,
) -> list[str]:
    """Build the docker run argument list. Does not call any subprocess."""
    cmd: list[str] = ['docker', 'run', '--rm']

    if hasattr(os, 'getuid'):  # POSIX only — Docker Desktop on Windows handles UID mapping via WSL2
        cmd += ['--user', f'{os.getuid()}:{os.getgid()}']  # type: ignore

    if interactive or shell or dev:
        cmd += ['--interactive', '--tty']

    entrypoint = 'bash' if shell else 'runzi'
    cmd += ['--entrypoint', entrypoint]

    if input_dir is not None:
        cmd += ['-v', f'{input_dir}:{_INPUT_FILES}:ro']

    cmd += ['-v', f'{aws_credentials}:{_AWS_CREDS_CONTAINER}:ro']

    if work_path is not None:
        cmd += ['-v', f'{work_path}:{_WORK_PATH_CONTAINER}']

    if ths_hazard is not None:
        cmd += ['-v', f'{ths_hazard}:/THS/HAZARD']

    if ths_disagg is not None:
        cmd += ['-v', f'{ths_disagg}:/THS/DISAGG']

    if dev and runzi_source is not None:
        cmd += ['-v', f'{runzi_source}:/app/nzshm-runzi']

    if toshi_home is not None:
        cmd += ['-v', f'{toshi_home}:{_TOSHI_HOME_CONTAINER}/.toshi:ro']
        # Override HOME so Path.home() in the container resolves to the mounted path.
        # The Python slim image sets HOME=/root but the container runs as a non-root
        # UID that cannot traverse /root (700); /toshi-home is accessible to any UID.
        env_vars = {**env_vars, 'HOME': _TOSHI_HOME_CONTAINER}

    cmd += ['-e', f'AWS_SHARED_CREDENTIALS_FILE={_AWS_CREDS_CONTAINER}']
    for key, value in env_vars.items():
        cmd += ['-e', f'{key}={value}']

    cmd.append(image)

    if not shell:
        cmd.extend(inner_args)

    return cmd


# ── Image helpers ─────────────────────────────────────────────────────────────


def _image_exists_locally(image: str) -> bool:
    result = subprocess.run(
        ['docker', 'image', 'inspect', image],
        capture_output=True,
    )
    return result.returncode == 0


def _ecr_login(region: str, aws_account_id: str) -> None:
    from runzi.cli.build_and_deploy_container import ecr_login

    ecr_login(region, aws_account_id)


def _resolve_image(dev: bool, image_override: str | None) -> str:
    if image_override:
        return image_override
    return _DEFAULT_DEV_IMAGE if dev else _DEFAULT_IMAGE


def _maybe_pull(image: str) -> None:
    if _image_exists_locally(image):
        return
    region = os.environ.get('AWS_REGION', _DEFAULT_AWS_REGION)
    account = os.environ.get('AWS_ACCOUNT_ID', _DEFAULT_AWS_ACCOUNT)
    repo = os.environ.get('ECR_REPO', _DEFAULT_ECR_REPO)
    if ":" not in image:  # guard againt no tag
        image += ":"
    ecr_image = f'{account}.dkr.ecr.{region}.amazonaws.com/{repo}:{image.split(":")[-1]}'
    rich_print(f'[yellow]Image {image!r} not found locally — pulling {ecr_image} from ECR[/yellow]')
    _ecr_login(region, account)
    subprocess.run(['docker', 'pull', ecr_image], check=True)
    subprocess.run(['docker', 'tag', ecr_image, image], check=True)


# ── Env resolution ────────────────────────────────────────────────────────────


def _collect_env_vars(extra: dict[str, str]) -> dict[str, str]:
    """Collect env vars to forward, from the current process environment."""
    result: dict[str, str] = {}
    for key, value in os.environ.items():
        if key in _ENV_FORWARDED_NZSHM_VARS or key in _ENV_PASSTHROUGH:
            result[key] = value
    result.update(extra)
    return result


def _resolve_ths(env_key: str) -> tuple[Path | None, dict[str, str]]:
    """Return (host_path_or_None, extra_env_to_forward)."""
    val = os.environ.get(env_key, '')
    if not val:
        return None, {}
    if val.startswith('s3://'):
        return None, {env_key: val}
    return Path(val), {}


def _resolve_toshi_home() -> Path | None:
    """Return host ~/.toshi/ path if it exists so Cognito credentials can be mounted."""
    p = Path.home() / '.toshi'
    if not p.exists():
        rich_print('[yellow]Warning: ~/.toshi/ not found — Cognito auth in container will not work[/yellow]')
        return None
    return p


def _resolve_work_path() -> Path | None:
    """Return the host work path to mount at /WORKING, or None if unset.

    Creates the directory if it doesn't exist so Docker doesn't auto-create it as root.
    """
    val = os.environ.get('NZSHM22_SCRIPT_WORK_PATH', '')
    if not val:
        return None
    p = Path(val).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


# ── Main entry point ──────────────────────────────────────────────────────────


def run_in_docker(
    inner_args: list[str],
    *,
    dev: bool = False,
    image: str | None = None,
    shell: bool = False,
    dry_run: bool = False,
) -> int:
    """Run a runzi invocation inside a local Docker container.

    Returns the container exit code (0 on success).
    """
    image_tag = _resolve_image(dev, image)

    if not dev:
        try:
            _maybe_pull(image_tag)
        except subprocess.CalledProcessError as exc:
            rich_print(f'[red]Failed to pull image: {exc}[/red]')
            return 1
    elif not _image_exists_locally(image_tag):
        rich_print(
            f'[red]Dev image {image_tag!r} not found. Build it first with:[/red]\n  runzi utils docker-build --dev ...'
        )
        return 1

    ths_hazard, ths_hazard_extra = _resolve_ths('NZSHM22_THS_RLZ_DB')
    ths_disagg, ths_disagg_extra = _resolve_ths('NZSHM22_THS_DISAGG_RLZ_DB')
    work_path = _resolve_work_path()
    toshi_home = _resolve_toshi_home()

    extra_env: dict[str, str] = {}
    extra_env.update(ths_hazard_extra)
    extra_env.update(ths_disagg_extra)

    # _collect_env_vars uses an explicit allowlist for NZSHM22_* vars, so image-set
    # path vars (THS, SCRIPT_WORK_PATH, OQ_*, OPENSHA_*, etc.) are never forwarded.
    # THS s3:// values are re-added via extra_env after the allowlist pass.
    env_vars = _collect_env_vars(extra_env)

    # Host UID is not in the container's /etc/passwd, so getpass.getuser() falls back
    # to pwd.getpwuid() and fails.  Ensure USER is set so the env-var path is taken.
    env_vars.setdefault('USER', os.environ.get('USER', 'runzi'))

    aws_credentials = Path.home() / '.aws' / 'credentials'
    if not aws_credentials.exists():
        rich_print(f'[yellow]Warning: AWS credentials not found at {aws_credentials}[/yellow]')

    runzi_source: Path | None = None
    if dev:
        import runzi

        runzi_source = Path(runzi.__file__).resolve().parents[1]

    input_dir: Path | None = None
    rewritten_args = inner_args

    if not shell and inner_args:
        # Resolve any args that are existing files to absolute paths upfront.
        # Docker mount sources must be absolute; a relative path like
        # `INPUT_FILES/foo.json` is otherwise treated as a named volume.
        normalized = [str(Path(arg).resolve()) if Path(arg).is_file() else arg for arg in inner_args]
        file_args = find_file_args(normalized)
        if file_args:
            input_dir = common_ancestor(file_args)
            rewritten_args = rewrite_file_args(normalized, file_args, input_dir)
        else:
            rewritten_args = inner_args
    elif shell:
        input_dir = Path.cwd()

    interactive = shell or dev

    cmd = build_docker_cmd(
        inner_args=rewritten_args,
        image=image_tag,
        dev=dev,
        shell=shell,
        aws_credentials=aws_credentials,
        ths_hazard=ths_hazard,
        ths_disagg=ths_disagg,
        env_vars=env_vars,
        input_dir=input_dir,
        runzi_source=runzi_source,
        interactive=interactive,
        work_path=work_path,
        toshi_home=toshi_home,
    )

    if dry_run:
        rich_print('[bold]docker command (dry run):[/bold]')
        print(' \\\n  '.join(cmd))
        return 0

    result = subprocess.run(cmd, check=False)
    return result.returncode


if __name__ == '__main__':
    sys.exit(run_in_docker(sys.argv[1:]))
