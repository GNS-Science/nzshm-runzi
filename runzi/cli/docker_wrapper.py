#!/usr/bin/env python3
"""Helpers for routing a runzi invocation through a local Docker container.

This module is also runnable as a standalone script
(``python3 docker_wrapper.py <runzi args>``) with only ``python3`` + ``docker`` +
``aws`` on PATH — no runzi install required.  To keep that path dependency-free,
``rich`` and ``python-dotenv`` are optional and degrade gracefully when absent.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

try:
    from rich import print as rich_print
except ImportError:  # standalone use without rich installed
    rich_print = print  # type: ignore[assignment]


def _parse_env_file(text: str) -> dict[str, str]:
    """Parse ``.env`` text into a dict (stdlib fallback for python-dotenv).

    Matches python-dotenv defaults for the common cases: skip blank/comment lines,
    ``KEY=VALUE`` only, strip an optional ``export`` prefix, strip a trailing inline
    comment from unquoted values, and strip surrounding quotes (a ``#`` inside a
    quoted value is kept verbatim).
    """
    result: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        key = key.strip()
        if key.startswith('export '):
            key = key[len('export ') :].strip()
        if key:
            value = value.strip()
            if value[:1] in ('"', "'") and (end := value.find(value[0], 1)) != -1:
                value = value[1:end]  # quoted: contents verbatim, drop any trailing comment
            else:
                hash_index = value.find(' #')  # unquoted: ' #' begins an inline comment
                if hash_index != -1:
                    value = value[:hash_index].rstrip()
                value = value.strip('\'"')
            result[key] = value
    return result


def _load_dotenv() -> None:
    """Load a ``.env`` from the current directory.

    Uses python-dotenv when available; otherwise falls back to :func:`_parse_env_file`
    so the standalone launcher needs no third-party dependency.  Does not override
    variables already set in the environment (matching python-dotenv defaults).
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        pass
    else:
        load_dotenv()
        return

    env_path = Path('.env')
    if not env_path.is_file():
        return
    for key, value in _parse_env_file(env_path.read_text()).items():
        os.environ.setdefault(key, value)


_load_dotenv()

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
        'NZSHM22_TOSHI_COGNITO_USER_POOL_ID',
        'NZSHM22_TOSHI_COGNITO_IDENTITY_POOL_ID',
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

# Default local image alias. Its tag (``prod``) doubles as the ECR tag pulled on each run
# (via _resolve_pull_source): the deploy pipeline publishes :prod, :experimental, and
# immutable version tags but never :latest, so :prod is the only sensible no-override
# default. Run a different published image with --docker-image (e.g.
# --docker-image <ecr-uri>/nzshm22/runzi:experimental).
_DEFAULT_IMAGE = 'runzi-build:prod'
_DEFAULT_ECR_REPO = 'nzshm22/runzi'
_DEFAULT_AWS_ACCOUNT = '461564345538'
_DEFAULT_AWS_REGION = 'us-east-1'

_INPUT_FILES = '/INPUT_FILES'
_AWS_CREDS_CONTAINER = '/aws-credentials'
_WORK_PATH_CONTAINER = '/WORKING'


# ── Docker meta-flag parsing ──────────────────────────────────────────────────
# These flags select/route the Docker execution; they are stripped before the
# remaining args are passed to runzi inside the container.  runzi_cli.py imports
# these for its Typer callback; the standalone __main__ below uses
# _parse_meta_flags.

_DOCKER_BOOL_FLAGS: frozenset[str] = frozenset(['--docker', '--docker-shell', '--docker-dry-run'])
_DOCKER_VALUE_FLAGS: frozenset[str] = frozenset(['--docker-image'])


def _strip_docker_flags(args: list[str]) -> list[str]:
    """Remove --docker-* flags (and their values) from a raw argv list."""
    result: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in _DOCKER_BOOL_FLAGS:
            pass  # drop boolean flag
        elif arg in _DOCKER_VALUE_FLAGS:
            i += 2  # drop --flag VALUE pair
            continue
        elif any(arg.startswith(f'{f}=') for f in _DOCKER_VALUE_FLAGS):
            pass  # drop --flag=value form
        else:
            result.append(arg)
        i += 1
    return result


def _parse_meta_flags(argv: list[str]) -> tuple[list[str], str | None, bool, bool]:
    """Parse the standalone launcher's docker meta-flags out of ``argv``.

    Returns ``(inner_args, image, shell, dry_run)``, mirroring the ``--docker*``
    options that ``runzi_cli.py`` exposes so the standalone script has parity with an
    installed ``runzi --docker...`` invocation.  A redundant ``--docker`` is a no-op
    here (we are already the docker launcher).
    """
    inner: list[str] = []
    shell = dry_run = False
    image: str | None = None
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == '--docker':
            pass  # redundant — this script *is* the docker launcher
        elif arg == '--docker-shell':
            shell = True
        elif arg == '--docker-dry-run':
            dry_run = True
        elif arg == '--docker-image':
            image = argv[i + 1] if i + 1 < len(argv) else None
            i += 2
            continue
        elif arg.startswith('--docker-image='):
            image = arg.split('=', 1)[1]
        else:
            inner.append(arg)
        i += 1
    return inner, image, shell, dry_run


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
    shell: bool,
    aws_credentials: Path,
    ths_hazard: Path | None,
    ths_disagg: Path | None,
    env_vars: dict[str, str],
    input_dir: Path | None = None,
    interactive: bool = False,
    work_path: Path | None = None,
    toshi_home: Path | None = None,
) -> list[str]:
    """Build the docker run argument list. Does not call any subprocess."""
    cmd: list[str] = ['docker', 'run', '--rm']

    if hasattr(os, 'getuid'):  # POSIX only — Docker Desktop on Windows handles UID mapping via WSL2
        cmd += ['--user', f'{os.getuid()}:{os.getgid()}']  # type: ignore

    if interactive or shell:
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

    if toshi_home is not None:
        # tmpfs gives a writable HOME: OQ can create HOME/oqdata on it.
        # The ~/.toshi/ directory is overlaid read-only inside the tmpfs so
        # Path.home()/'.toshi'/'credentials' is accessible to the toshi client.
        cmd += ['--mount', f'type=tmpfs,destination={_TOSHI_HOME_CONTAINER},tmpfs-mode=0777']
        cmd += ['-v', f'{toshi_home}:{_TOSHI_HOME_CONTAINER}/.toshi:ro']
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
    """Log Docker into ECR using the AWS CLI. Inlined so the standalone launcher
    has no runzi-internal import (mirrors build_and_deploy_container.ecr_login)."""
    rich_print('Logging into ECR...')
    registry = f'{aws_account_id}.dkr.ecr.{region}.amazonaws.com'
    subprocess.run(
        f'aws ecr get-login-password --region {region} | docker login --username AWS --password-stdin {registry}',
        shell=True,
        check=True,
    )


def _resolve_image(image_override: str | None) -> str:
    if image_override:
        return image_override
    return _DEFAULT_IMAGE


# <account>.dkr.ecr.<region>.amazonaws.com — used to derive login account/region
# from a fully-qualified ECR image reference.
_ECR_HOST_RE = re.compile(r'^(?P<account>\d+)\.dkr\.ecr\.(?P<region>[a-z0-9-]+)\.amazonaws\.com$')


def _resolve_pull_source(image: str) -> tuple[str, str | None, str | None]:
    """Return ``(pull_source, login_region, login_account)`` for an image reference.

    A fully-qualified registry reference (host[:port]/path, per Docker's rule that the
    component before the first ``/`` contains a ``.`` or ``:``) is pulled verbatim; the
    ECR account/region are parsed from its host for login (``None`` for a non-ECR host,
    which skips ECR login).  A bare name/tag is reconstructed against the configured
    default ECR account/region/repo, keeping only its tag.
    """
    head = image.split('/', 1)[0]
    if '/' in image and ('.' in head or ':' in head):
        m = _ECR_HOST_RE.match(head)
        if m:
            return image, m.group('region'), m.group('account')
        return image, None, None
    region = os.environ.get('AWS_REGION', _DEFAULT_AWS_REGION)
    account = os.environ.get('AWS_ACCOUNT_ID', _DEFAULT_AWS_ACCOUNT)
    repo = os.environ.get('ECR_REPO', _DEFAULT_ECR_REPO)
    tag = image.split(':', 1)[1] if ':' in image else 'latest'
    return f'{account}.dkr.ecr.{region}.amazonaws.com/{repo}:{tag}', region, account


def _maybe_pull(image: str) -> None:
    """Refresh ``image`` from its registry before each run.

    ``:prod`` / ``:experimental`` are floating tags that a new deploy re-points to a new
    digest, so we pull every time rather than only when the image is absent — otherwise a
    stale local copy under the same tag would be used indefinitely.  ``docker pull`` only
    transfers layers whose digest changed, so it is a cheap no-op (a registry manifest
    check, no blob download) when the local image already matches the remote digest.

    If the registry can't be reached (offline, expired creds) but a copy of ``image`` is
    already cached locally, fall back to it with a warning instead of failing the run.
    """
    source, region, account = _resolve_pull_source(image)
    try:
        if region and account:
            _ecr_login(region, account)
        subprocess.run(['docker', 'pull', source], check=True)
    except subprocess.CalledProcessError:
        if _image_exists_locally(image):
            rich_print(f'[yellow]Could not reach the registry to refresh {image!r}; using the cached image.[/yellow]')
            return
        raise
    if source != image:
        subprocess.run(['docker', 'tag', source, image], check=True)


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
    """Return host ~/.toshi/ path if the directory exists, else warn and return None."""
    p = Path.home() / '.toshi'
    if not p.exists():
        rich_print(
            '[yellow]Warning: ~/.toshi/ not found — '
            'Cognito auth in container will not work. Run: toshi-auth login[/yellow]'
        )
        return None
    if not (p / 'credentials').exists():
        rich_print(
            '[yellow]Warning: ~/.toshi/credentials not found — '
            'Cognito auth in container will not work. Run: toshi-auth login[/yellow]'
        )
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
    image: str | None = None,
    shell: bool = False,
    dry_run: bool = False,
) -> int:
    """Run a runzi invocation inside a local Docker container.

    Returns the container exit code (0 on success).
    """
    image_tag = _resolve_image(image)

    try:
        _maybe_pull(image_tag)
    except subprocess.CalledProcessError as exc:
        rich_print(f'[red]Failed to pull image: {exc}[/red]')
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

    interactive = shell

    cmd = build_docker_cmd(
        inner_args=rewritten_args,
        image=image_tag,
        shell=shell,
        aws_credentials=aws_credentials,
        ths_hazard=ths_hazard,
        ths_disagg=ths_disagg,
        env_vars=env_vars,
        input_dir=input_dir,
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
    _inner, _image, _shell, _dry_run = _parse_meta_flags(sys.argv[1:])
    sys.exit(run_in_docker(_inner, image=_image, shell=_shell, dry_run=_dry_run))
