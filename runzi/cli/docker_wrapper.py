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
_ENV_PREFIX_PASSTHROUGH = 'NZSHM22_'

_DEFAULT_IMAGE = 'runzi-build:latest'
_DEFAULT_DEV_IMAGE = 'runzi-build:dev'
_DEFAULT_ECR_REPO = 'nzshm22/runzi'
_DEFAULT_AWS_ACCOUNT = '461564345538'
_DEFAULT_AWS_REGION = 'us-east-1'

_INPUT_FILES = '/INPUT_FILES'
_AWS_CREDS_CONTAINER = '/aws-credentials'


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
            result.append(f'{_INPUT_FILES}/{rel}')
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
) -> list[str]:
    """Build the docker run argument list. Does not call any subprocess."""
    cmd: list[str] = ['docker', 'run', '--rm']

    cmd += ['--user', f'{os.getuid()}:{os.getgid()}']

    if interactive or shell or dev:
        cmd += ['--interactive', '--tty']

    entrypoint = 'bash' if shell else 'runzi'
    cmd += ['--entrypoint', entrypoint]

    if input_dir is not None:
        cmd += ['-v', f'{input_dir}:{_INPUT_FILES}:ro']

    cmd += ['-v', f'{aws_credentials}:{_AWS_CREDS_CONTAINER}:ro']

    if ths_hazard is not None:
        cmd += ['-v', f'{ths_hazard}:/THS/HAZARD']

    if ths_disagg is not None:
        cmd += ['-v', f'{ths_disagg}:/THS/DISAGG']

    if dev and runzi_source is not None:
        cmd += ['-v', f'{runzi_source}:/app/nzshm-runzi']

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
        if key.startswith(_ENV_PREFIX_PASSTHROUGH) or key in _ENV_PASSTHROUGH:
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
            f'[red]Dev image {image_tag!r} not found. Build it first with:[/red]\n  runzi utils container --dev ...'
        )
        return 1

    ths_hazard, ths_hazard_extra = _resolve_ths('NZSHM22_THS_RLZ_DB')
    ths_disagg, ths_disagg_extra = _resolve_ths('NZSHM22_THS_DISAGG_RLZ_DB')

    extra_env: dict[str, str] = {}
    extra_env.update(ths_hazard_extra)
    extra_env.update(ths_disagg_extra)

    env_vars = _collect_env_vars(extra_env)
    # Remove THS vars from forwarded env if they're host paths (image already has defaults)
    env_vars.pop('NZSHM22_THS_RLZ_DB', None)
    env_vars.pop('NZSHM22_THS_DISAGG_RLZ_DB', None)
    if ths_hazard_extra:
        env_vars.update(ths_hazard_extra)
    if ths_disagg_extra:
        env_vars.update(ths_disagg_extra)

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
        file_args = find_file_args(inner_args)
        if file_args:
            input_dir = common_ancestor(file_args)
            rewritten_args = rewrite_file_args(inner_args, file_args, input_dir)
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
    )

    if dry_run:
        rich_print('[bold]docker command (dry run):[/bold]')
        rich_print(' \\\n  '.join(cmd))
        return 0

    result = subprocess.run(cmd, check=False)
    return result.returncode


if __name__ == '__main__':
    sys.exit(run_in_docker(sys.argv[1:]))
