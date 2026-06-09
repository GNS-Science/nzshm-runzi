"""Tests for the docker_wrapper module — TDD (RED phase first)."""

import os
import re

import pytest
from typer.testing import CliRunner

from runzi.cli import docker_wrapper
from runzi.cli.runzi_cli import app

runner = CliRunner(env={"NO_COLOR": "1", "LANG": "en_US.UTF-8"})

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences so plain-text assertions are CI-safe."""
    return _ANSI_RE.sub('', text)


# ── Helpers ──────────────────────────────────────────────────────────────────


def has_flag(cmd: list[str], flag: str) -> bool:
    return flag in cmd


def has_volume(cmd: list[str], mount_spec: str) -> bool:
    """Check that -v <mount_spec> appears as consecutive elements."""
    for i, arg in enumerate(cmd):
        if arg == '-v' and i + 1 < len(cmd) and cmd[i + 1] == mount_spec:
            return True
    return False


def has_env(cmd: list[str], key: str, value: str | None = None) -> bool:
    """Check that -e KEY or -e KEY=VALUE appears in cmd."""
    for i, arg in enumerate(cmd):
        if arg == '-e' and i + 1 < len(cmd):
            entry = cmd[i + 1]
            if value is None and entry.startswith(f'{key}'):
                return True
            if entry == f'{key}={value}':
                return True
    return False


def flag_value(cmd: list[str], flag: str) -> str | None:
    """Return the value after a flag, or None."""
    try:
        idx = cmd.index(flag)
        return cmd[idx + 1]
    except (ValueError, IndexError):
        return None


# ── find_file_args ────────────────────────────────────────────────────────────


def test_find_file_args_returns_empty_for_no_args():
    assert docker_wrapper.find_file_args([]) == []


def test_find_file_args_ignores_non_path_strings():
    assert docker_wrapper.find_file_args(['hazard', 'oq-hazard', '--help']) == []


def test_find_file_args_detects_existing_file(tmp_path):
    config = tmp_path / 'foo.json'
    config.write_text('{}')
    result = docker_wrapper.find_file_args(['hazard', 'oq-hazard', str(config)])
    assert result == [config]


def test_find_file_args_detects_multiple_files(tmp_path):
    sub = tmp_path / 'sub'
    sub.mkdir()
    a = tmp_path / 'a.json'
    b = sub / 'b.json'
    a.write_text('{}')
    b.write_text('{}')
    result = docker_wrapper.find_file_args(['hazard', str(a), str(b)])
    assert result == [a, b]


def test_find_file_args_ignores_nonexistent_paths():
    result = docker_wrapper.find_file_args(['/does/not/exist.json'])
    assert result == []


# ── common_ancestor ───────────────────────────────────────────────────────────


def test_common_ancestor_single_file(tmp_path):
    f = tmp_path / 'foo.json'
    assert docker_wrapper.common_ancestor([f]) == tmp_path


def test_common_ancestor_files_in_same_dir(tmp_path):
    a = tmp_path / 'a.json'
    b = tmp_path / 'b.json'
    assert docker_wrapper.common_ancestor([a, b]) == tmp_path


def test_common_ancestor_files_in_subdirs(tmp_path):
    sub = tmp_path / 'sub'
    a = tmp_path / 'a.json'
    b = sub / 'b.json'
    assert docker_wrapper.common_ancestor([a, b]) == tmp_path


def test_common_ancestor_deep_subdirs(tmp_path):
    d1 = tmp_path / 'configs' / 'hazard'
    d2 = tmp_path / 'configs' / 'disagg'
    a = d1 / 'a.json'
    b = d2 / 'b.json'
    assert docker_wrapper.common_ancestor([a, b]) == tmp_path / 'configs'


# ── rewrite_file_args ─────────────────────────────────────────────────────────


def test_rewrite_file_args_single_file_in_root(tmp_path):
    f = tmp_path / 'foo.json'
    args = ['hazard', 'oq-hazard', str(f)]
    result = docker_wrapper.rewrite_file_args(args, [f], tmp_path)
    assert result == ['hazard', 'oq-hazard', '/INPUT_FILES/foo.json']


def test_rewrite_file_args_file_in_subdir(tmp_path):
    sub = tmp_path / 'configs'
    f = sub / 'foo.json'
    args = ['hazard', 'oq-hazard', str(f)]
    result = docker_wrapper.rewrite_file_args(args, [f], tmp_path)
    assert result == ['hazard', 'oq-hazard', '/INPUT_FILES/configs/foo.json']


def test_rewrite_file_args_multiple_files(tmp_path):
    sub = tmp_path / 'sub'
    a = tmp_path / 'a.json'
    b = sub / 'b.json'
    args = ['hazard', str(a), str(b)]
    result = docker_wrapper.rewrite_file_args(args, [a, b], tmp_path)
    assert result == ['hazard', '/INPUT_FILES/a.json', '/INPUT_FILES/sub/b.json']


def test_rewrite_file_args_leaves_non_file_args_unchanged(tmp_path):
    f = tmp_path / 'foo.json'
    args = ['hazard', 'oq-hazard', '--some-flag', str(f)]
    result = docker_wrapper.rewrite_file_args(args, [f], tmp_path)
    assert result == ['hazard', 'oq-hazard', '--some-flag', '/INPUT_FILES/foo.json']


# ── build_docker_cmd ──────────────────────────────────────────────────────────


@pytest.fixture()
def aws_creds(tmp_path):
    creds = tmp_path / 'credentials'
    creds.write_text('[default]\naws_access_key_id = test')
    return creds


def test_build_docker_cmd_starts_with_docker_run(tmp_path, aws_creds):
    cmd = docker_wrapper.build_docker_cmd(
        inner_args=[],
        image='runzi-build:latest',
        dev=False,
        shell=True,
        aws_credentials=aws_creds,
        ths_hazard=None,
        ths_disagg=None,
        env_vars={},
    )
    assert cmd[:2] == ['docker', 'run']


def test_build_docker_cmd_has_rm_flag(tmp_path, aws_creds):
    cmd = docker_wrapper.build_docker_cmd(
        inner_args=[],
        image='runzi-build:latest',
        dev=False,
        shell=True,
        aws_credentials=aws_creds,
        ths_hazard=None,
        ths_disagg=None,
        env_vars={},
    )
    assert '--rm' in cmd


@pytest.mark.skipif(not hasattr(os, 'getuid'), reason='POSIX-only --user mapping')
def test_build_docker_cmd_has_user_flag(aws_creds):
    cmd = docker_wrapper.build_docker_cmd(
        inner_args=[],
        image='runzi-build:latest',
        dev=False,
        shell=True,
        aws_credentials=aws_creds,
        ths_hazard=None,
        ths_disagg=None,
        env_vars={},
    )
    expected_user = f'{os.getuid()}:{os.getgid()}'
    assert flag_value(cmd, '--user') == expected_user


def test_build_docker_cmd_mounts_aws_credentials(aws_creds):
    cmd = docker_wrapper.build_docker_cmd(
        inner_args=[],
        image='runzi-build:latest',
        dev=False,
        shell=True,
        aws_credentials=aws_creds,
        ths_hazard=None,
        ths_disagg=None,
        env_vars={},
    )
    assert has_volume(cmd, f'{aws_creds}:/aws-credentials:ro')


def test_build_docker_cmd_sets_aws_creds_env(aws_creds):
    cmd = docker_wrapper.build_docker_cmd(
        inner_args=[],
        image='runzi-build:latest',
        dev=False,
        shell=True,
        aws_credentials=aws_creds,
        ths_hazard=None,
        ths_disagg=None,
        env_vars={},
    )
    assert has_env(cmd, 'AWS_SHARED_CREDENTIALS_FILE', '/aws-credentials')


def test_build_docker_cmd_shell_uses_bash_entrypoint(aws_creds):
    cmd = docker_wrapper.build_docker_cmd(
        inner_args=[],
        image='runzi-build:latest',
        dev=False,
        shell=True,
        aws_credentials=aws_creds,
        ths_hazard=None,
        ths_disagg=None,
        env_vars={},
    )
    assert flag_value(cmd, '--entrypoint') == 'bash'


def test_build_docker_cmd_passthrough_uses_runzi_entrypoint(tmp_path, aws_creds):
    cmd = docker_wrapper.build_docker_cmd(
        inner_args=['hazard', 'oq-hazard', '/INPUT_FILES/foo.json'],
        image='runzi-build:latest',
        dev=False,
        shell=False,
        aws_credentials=aws_creds,
        ths_hazard=None,
        ths_disagg=None,
        env_vars={},
        input_dir=tmp_path,
    )
    assert flag_value(cmd, '--entrypoint') == 'runzi'


def test_build_docker_cmd_passthrough_appends_runzi_args(tmp_path, aws_creds):
    inner = ['hazard', 'oq-hazard', '/INPUT_FILES/foo.json']
    cmd = docker_wrapper.build_docker_cmd(
        inner_args=inner,
        image='runzi-build:latest',
        dev=False,
        shell=False,
        aws_credentials=aws_creds,
        ths_hazard=None,
        ths_disagg=None,
        env_vars={},
        input_dir=tmp_path,
    )
    # inner args appear at the end after the image
    image_idx = cmd.index('runzi-build:latest')
    assert cmd[image_idx + 1 :] == inner


def test_build_docker_cmd_mounts_input_dir(tmp_path, aws_creds):
    cmd = docker_wrapper.build_docker_cmd(
        inner_args=[],
        image='runzi-build:latest',
        dev=False,
        shell=True,
        aws_credentials=aws_creds,
        ths_hazard=None,
        ths_disagg=None,
        env_vars={},
        input_dir=tmp_path,
    )
    assert has_volume(cmd, f'{tmp_path}:/INPUT_FILES:ro')


def test_build_docker_cmd_no_input_dir_no_input_files_mount(aws_creds):
    cmd = docker_wrapper.build_docker_cmd(
        inner_args=[],
        image='runzi-build:latest',
        dev=False,
        shell=True,
        aws_credentials=aws_creds,
        ths_hazard=None,
        ths_disagg=None,
        env_vars={},
        input_dir=None,
    )
    assert '/INPUT_FILES' not in ' '.join(cmd)


def test_build_docker_cmd_mounts_ths_dirs(tmp_path, aws_creds):
    ths_h = tmp_path / 'hazard'
    ths_d = tmp_path / 'disagg'
    cmd = docker_wrapper.build_docker_cmd(
        inner_args=[],
        image='runzi-build:latest',
        dev=False,
        shell=True,
        aws_credentials=aws_creds,
        ths_hazard=ths_h,
        ths_disagg=ths_d,
        env_vars={},
    )
    assert has_volume(cmd, f'{ths_h}:/THS/HAZARD')
    assert has_volume(cmd, f'{ths_d}:/THS/DISAGG')


def test_build_docker_cmd_skips_ths_mounts_when_none(aws_creds):
    cmd = docker_wrapper.build_docker_cmd(
        inner_args=[],
        image='runzi-build:latest',
        dev=False,
        shell=True,
        aws_credentials=aws_creds,
        ths_hazard=None,
        ths_disagg=None,
        env_vars={},
    )
    assert '/THS/HAZARD' not in ' '.join(cmd)
    assert '/THS/DISAGG' not in ' '.join(cmd)


def test_build_docker_cmd_dev_mounts_runzi_source(tmp_path, aws_creds):
    src = tmp_path / 'nzshm-runzi'
    src.mkdir()
    cmd = docker_wrapper.build_docker_cmd(
        inner_args=[],
        image='runzi-build:dev',
        dev=True,
        shell=True,
        aws_credentials=aws_creds,
        ths_hazard=None,
        ths_disagg=None,
        env_vars={},
        runzi_source=src,
    )
    assert has_volume(cmd, f'{src}:/app/nzshm-runzi')


def test_build_docker_cmd_non_dev_does_not_mount_source(aws_creds):
    cmd = docker_wrapper.build_docker_cmd(
        inner_args=[],
        image='runzi-build:latest',
        dev=False,
        shell=True,
        aws_credentials=aws_creds,
        ths_hazard=None,
        ths_disagg=None,
        env_vars={},
        runzi_source=None,
    )
    assert '/app/nzshm-runzi' not in ' '.join(cmd)


def test_build_docker_cmd_forwards_env_vars(aws_creds):
    env = {'NZSHM22_TOSHI_API_URL': 'http://api', 'AWS_PROFILE': 'myprofile'}
    cmd = docker_wrapper.build_docker_cmd(
        inner_args=[],
        image='runzi-build:latest',
        dev=False,
        shell=True,
        aws_credentials=aws_creds,
        ths_hazard=None,
        ths_disagg=None,
        env_vars=env,
    )
    assert has_env(cmd, 'NZSHM22_TOSHI_API_URL', 'http://api')
    assert has_env(cmd, 'AWS_PROFILE', 'myprofile')


def test_build_docker_cmd_image_at_end_before_args(aws_creds):
    cmd = docker_wrapper.build_docker_cmd(
        inner_args=['hazard', 'oq-hazard'],
        image='runzi-build:latest',
        dev=False,
        shell=False,
        aws_credentials=aws_creds,
        ths_hazard=None,
        ths_disagg=None,
        env_vars={},
    )
    image_idx = cmd.index('runzi-build:latest')
    assert cmd[image_idx + 1 :] == ['hazard', 'oq-hazard']


# ── CLI integration ───────────────────────────────────────────────────────────


def test_cli_help_shows_docker_flag():
    result = runner.invoke(app, ['--help'])
    assert '--docker' in strip_ansi(result.output)


def test_cli_docker_flag_invokes_wrapper(mocker, tmp_path):
    config = tmp_path / 'foo.json'
    config.write_text('{}')
    mock_run = mocker.patch('runzi.cli.docker_wrapper.run_in_docker', return_value=0)
    result = runner.invoke(app, ['--docker', 'hazard', 'oq-hazard', str(config)])
    mock_run.assert_called_once()
    assert result.exit_code == 0


def test_cli_docker_dev_implies_docker(mocker, tmp_path):
    config = tmp_path / 'foo.json'
    config.write_text('{}')
    mock_run = mocker.patch('runzi.cli.docker_wrapper.run_in_docker', return_value=0)
    runner.invoke(app, ['--docker-dev', 'hazard', 'oq-hazard', str(config)])
    mock_run.assert_called_once()
    call_kwargs = mock_run.call_args
    assert call_kwargs.kwargs.get('dev') is True or (call_kwargs.args and call_kwargs.args[1] is True)


def test_cli_docker_shell_implies_docker(mocker):
    mock_run = mocker.patch('runzi.cli.docker_wrapper.run_in_docker', return_value=0)
    runner.invoke(app, ['--docker-shell'])
    mock_run.assert_called_once()


def test_cli_no_docker_flag_does_not_invoke_wrapper(mocker):
    mock_run = mocker.patch('runzi.cli.docker_wrapper.run_in_docker', return_value=0)
    runner.invoke(app, ['hazard', 'oq-hazard', '--help'])
    mock_run.assert_not_called()


def test_cli_docker_drops_host_script_work_path_env(mocker, tmp_path, monkeypatch):
    """Host NZSHM22_SCRIPT_WORK_PATH must not be forwarded as an env var."""
    (tmp_path / 'foo.json').write_text('{}')
    monkeypatch.chdir(tmp_path)
    work = tmp_path / 'work'
    monkeypatch.setenv('NZSHM22_SCRIPT_WORK_PATH', str(work))

    captured: dict = {}

    def fake_run(cmd, check=False):
        captured['cmd'] = cmd

        class R:
            returncode = 0

        return R()

    mocker.patch('runzi.cli.docker_wrapper._maybe_pull')
    mocker.patch('runzi.cli.docker_wrapper.subprocess.run', side_effect=fake_run)
    result = runner.invoke(app, ['--docker', 'hazard', 'oq-hazard', 'foo.json'])
    assert result.exit_code == 0
    assert not has_env(captured['cmd'], 'NZSHM22_SCRIPT_WORK_PATH'), (
        f'host NZSHM22_SCRIPT_WORK_PATH leaked into container: {captured["cmd"]}'
    )


def test_cli_docker_mounts_script_work_path(mocker, tmp_path, monkeypatch):
    """Host NZSHM22_SCRIPT_WORK_PATH is mounted at /WORKING read-write."""
    (tmp_path / 'foo.json').write_text('{}')
    monkeypatch.chdir(tmp_path)
    work = tmp_path / 'work'
    monkeypatch.setenv('NZSHM22_SCRIPT_WORK_PATH', str(work))

    captured: dict = {}

    def fake_run(cmd, check=False):
        captured['cmd'] = cmd

        class R:
            returncode = 0

        return R()

    mocker.patch('runzi.cli.docker_wrapper._maybe_pull')
    mocker.patch('runzi.cli.docker_wrapper.subprocess.run', side_effect=fake_run)
    result = runner.invoke(app, ['--docker', 'hazard', 'oq-hazard', 'foo.json'])
    assert result.exit_code == 0
    assert has_volume(captured['cmd'], f'{work}:/WORKING'), f'work-path mount missing or wrong: {captured["cmd"]}'
    assert work.is_dir()


def test_cli_docker_no_work_path_mount_when_unset(mocker, tmp_path, monkeypatch):
    """When host has no NZSHM22_SCRIPT_WORK_PATH, no /WORKING mount is added."""
    (tmp_path / 'foo.json').write_text('{}')
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('NZSHM22_SCRIPT_WORK_PATH', raising=False)

    captured: dict = {}

    def fake_run(cmd, check=False):
        captured['cmd'] = cmd

        class R:
            returncode = 0

        return R()

    mocker.patch('runzi.cli.docker_wrapper._maybe_pull')
    mocker.patch('runzi.cli.docker_wrapper.subprocess.run', side_effect=fake_run)
    result = runner.invoke(app, ['--docker', 'hazard', 'oq-hazard', 'foo.json'])
    assert result.exit_code == 0
    assert '/WORKING' not in ' '.join(captured['cmd'])


def test_cli_docker_drops_image_path_env_vars(mocker, tmp_path, monkeypatch):
    """Image-set path vars must not be forwarded to the container."""
    (tmp_path / 'foo.json').write_text('{}')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('NZSHM22_OPENSHA_ROOT', '/host/opensha')
    monkeypatch.setenv('NZSHM22_FATJAR', '/host/foo.jar')
    monkeypatch.setenv('NZSHM22_OPENSHA_JRE', '/host/java')
    monkeypatch.setenv('NZSHM22_OQ_VENV', '/host/oq-venv')
    monkeypatch.setenv('NZSHM22_OQ_DATADIR', '/host/oqdata')

    captured: dict = {}

    def fake_run(cmd, check=False):
        captured['cmd'] = cmd

        class R:
            returncode = 0

        return R()

    mocker.patch('runzi.cli.docker_wrapper._maybe_pull')
    mocker.patch('runzi.cli.docker_wrapper.subprocess.run', side_effect=fake_run)
    result = runner.invoke(app, ['--docker', 'hazard', 'oq-hazard', 'foo.json'])
    assert result.exit_code == 0
    for var in (
        'NZSHM22_OPENSHA_ROOT',
        'NZSHM22_FATJAR',
        'NZSHM22_OPENSHA_JRE',
        'NZSHM22_OQ_VENV',
        'NZSHM22_OQ_DATADIR',
    ):
        assert not has_env(captured['cmd'], var), f'{var} leaked into container'


def test_cli_docker_forwards_allowlisted_nzshm_vars(mocker, tmp_path, monkeypatch):
    """Non-path NZSHM22 vars on the allowlist are still forwarded."""
    (tmp_path / 'foo.json').write_text('{}')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('NZSHM22_TOSHI_API_URL', 'http://api.example/graphql')
    monkeypatch.setenv('NZSHM22_BUILD_PLOTS', 'TRUE')

    captured: dict = {}

    def fake_run(cmd, check=False):
        captured['cmd'] = cmd

        class R:
            returncode = 0

        return R()

    mocker.patch('runzi.cli.docker_wrapper._maybe_pull')
    mocker.patch('runzi.cli.docker_wrapper.subprocess.run', side_effect=fake_run)
    result = runner.invoke(app, ['--docker', 'hazard', 'oq-hazard', 'foo.json'])
    assert result.exit_code == 0
    assert has_env(captured['cmd'], 'NZSHM22_TOSHI_API_URL', 'http://api.example/graphql')
    assert has_env(captured['cmd'], 'NZSHM22_BUILD_PLOTS', 'TRUE')


def test_cli_docker_forwards_cognito_user_pool_id(mocker, tmp_path, monkeypatch):
    """NZSHM22_TOSHI_COGNITO_USER_POOL_ID must be forwarded so load_cognito_config
    can resolve user_pool_id inside the container without falling back to the
    auth_config.json file."""
    (tmp_path / 'foo.json').write_text('{}')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('NZSHM22_TOSHI_COGNITO_USER_POOL_ID', 'ap-southeast-2_FAKE')

    captured: dict = {}

    def fake_run(cmd, check=False):
        captured['cmd'] = cmd

        class R:
            returncode = 0

        return R()

    mocker.patch('runzi.cli.docker_wrapper._maybe_pull')
    mocker.patch('runzi.cli.docker_wrapper.subprocess.run', side_effect=fake_run)
    result = runner.invoke(app, ['--docker', 'hazard', 'oq-hazard', 'foo.json'])
    assert result.exit_code == 0
    assert has_env(captured['cmd'], 'NZSHM22_TOSHI_COGNITO_USER_POOL_ID', 'ap-southeast-2_FAKE')


def test_cli_docker_forwards_cognito_identity_pool_id(mocker, tmp_path, monkeypatch):
    """NZSHM22_TOSHI_COGNITO_IDENTITY_POOL_ID must be forwarded so load_cognito_config
    can resolve identity_pool_id inside the container without requiring an
    auth_config.json file mounted in."""
    (tmp_path / 'foo.json').write_text('{}')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('NZSHM22_TOSHI_COGNITO_IDENTITY_POOL_ID', 'ap-southeast-2:fake-pool')

    captured: dict = {}

    def fake_run(cmd, check=False):
        captured['cmd'] = cmd

        class R:
            returncode = 0

        return R()

    mocker.patch('runzi.cli.docker_wrapper._maybe_pull')
    mocker.patch('runzi.cli.docker_wrapper.subprocess.run', side_effect=fake_run)
    result = runner.invoke(app, ['--docker', 'hazard', 'oq-hazard', 'foo.json'])
    assert result.exit_code == 0
    assert has_env(captured['cmd'], 'NZSHM22_TOSHI_COGNITO_IDENTITY_POOL_ID', 'ap-southeast-2:fake-pool')


def test_cli_docker_does_not_forward_m2m_secret_arn(mocker, tmp_path, monkeypatch):
    """NZSHM22_TOSHI_M2M_SECRET_ARN must never be forwarded into a local --docker container.

    M2M auth is a Batch-job-definition concern only. Forwarding this var would cause
    the client to select M2M auth and silently override the mounted ~/.toshi/credentials,
    breaking Scientist (interactive) auth for local docker runs.
    """
    (tmp_path / 'foo.json').write_text('{}')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('NZSHM22_TOSHI_M2M_SECRET_ARN', 'arn:aws:secretsmanager:ap-southeast-2:123:secret/fake')

    captured: dict = {}

    def fake_run(cmd, check=False):
        captured['cmd'] = cmd

        class R:
            returncode = 0

        return R()

    mocker.patch('runzi.cli.docker_wrapper._maybe_pull')
    mocker.patch('runzi.cli.docker_wrapper.subprocess.run', side_effect=fake_run)
    result = runner.invoke(app, ['--docker', 'hazard', 'oq-hazard', 'foo.json'])
    assert result.exit_code == 0
    assert not has_env(captured['cmd'], 'NZSHM22_TOSHI_M2M_SECRET_ARN'), (
        'NZSHM22_TOSHI_M2M_SECRET_ARN must not be forwarded to local docker containers; '
        'M2M config must be supplied by the Batch job definition only.'
    )


def test_cli_docker_ths_s3_value_still_forwarded(mocker, tmp_path, monkeypatch):
    """THS s3:// value is forwarded via extra_env even though THS is not in the allowlist."""
    (tmp_path / 'foo.json').write_text('{}')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('NZSHM22_THS_RLZ_DB', 's3://my-bucket/path')

    captured: dict = {}

    def fake_run(cmd, check=False):
        captured['cmd'] = cmd

        class R:
            returncode = 0

        return R()

    mocker.patch('runzi.cli.docker_wrapper._maybe_pull')
    mocker.patch('runzi.cli.docker_wrapper.subprocess.run', side_effect=fake_run)
    result = runner.invoke(app, ['--docker', 'hazard', 'oq-hazard', 'foo.json'])
    assert result.exit_code == 0
    assert has_env(captured['cmd'], 'NZSHM22_THS_RLZ_DB', 's3://my-bucket/path')


def test_cli_docker_sets_user_env_in_container(mocker, tmp_path, monkeypatch):
    """USER must be forwarded so getpass.getuser() doesn't fall back to pwd.getpwuid()."""
    (tmp_path / 'foo.json').write_text('{}')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('USER', 'host-user')

    captured: dict = {}

    def fake_run(cmd, check=False):
        captured['cmd'] = cmd

        class R:
            returncode = 0

        return R()

    mocker.patch('runzi.cli.docker_wrapper._maybe_pull')
    mocker.patch('runzi.cli.docker_wrapper.subprocess.run', side_effect=fake_run)
    result = runner.invoke(app, ['--docker', 'hazard', 'oq-hazard', 'foo.json'])
    assert result.exit_code == 0
    assert has_env(captured['cmd'], 'USER', 'host-user'), f'USER missing from cmd: {captured["cmd"]}'


def test_cli_docker_sets_default_user_when_host_unset(mocker, tmp_path, monkeypatch):
    """When host has no USER, a fallback value is still forwarded to the container."""
    (tmp_path / 'foo.json').write_text('{}')
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('USER', raising=False)

    captured: dict = {}

    def fake_run(cmd, check=False):
        captured['cmd'] = cmd

        class R:
            returncode = 0

        return R()

    mocker.patch('runzi.cli.docker_wrapper._maybe_pull')
    mocker.patch('runzi.cli.docker_wrapper.subprocess.run', side_effect=fake_run)
    result = runner.invoke(app, ['--docker', 'hazard', 'oq-hazard', 'foo.json'])
    assert result.exit_code == 0
    assert has_env(captured['cmd'], 'USER', 'runzi'), f'fallback USER missing: {captured["cmd"]}'


def test_cli_docker_resolves_relative_path_to_absolute_mount(mocker, tmp_path, monkeypatch):
    """Relative-path file args must produce an absolute -v mount source."""
    sub = tmp_path / 'sub'
    sub.mkdir()
    (sub / 'foo.json').write_text('{}')
    monkeypatch.chdir(tmp_path)

    captured: dict = {}

    def fake_run(cmd, check=False):
        captured['cmd'] = cmd

        class R:
            returncode = 0

        return R()

    mocker.patch('runzi.cli.docker_wrapper._maybe_pull')
    mocker.patch('runzi.cli.docker_wrapper.subprocess.run', side_effect=fake_run)
    result = runner.invoke(app, ['--docker', 'hazard', 'oq-hazard', 'sub/foo.json'])
    assert result.exit_code == 0
    cmd = captured['cmd']
    expected_mount = f'{(tmp_path / "sub").resolve()}:/INPUT_FILES:ro'
    assert expected_mount in cmd, f'expected absolute mount, got cmd: {cmd}'
    assert '/INPUT_FILES/foo.json' in cmd


def test_cli_docker_dry_run_uses_absolute_mount_for_relative_file(mocker, tmp_path, monkeypatch):
    """--docker-dry-run output must reference the absolute path for a relative file arg."""
    (tmp_path / 'foo.json').write_text('{}')
    monkeypatch.chdir(tmp_path)
    mocker.patch('runzi.cli.docker_wrapper._maybe_pull')
    result = runner.invoke(app, ['--docker-dry-run', 'hazard', 'oq-hazard', 'foo.json'])
    assert result.exit_code == 0
    assert str(tmp_path.resolve()) in strip_ansi(result.output)
    assert '/INPUT_FILES/foo.json' in strip_ansi(result.output)


def test_cli_docker_forwards_subcommand_name_in_inner_args(mocker, tmp_path):
    """Regression: --docker must include the subcommand name in inner_args.

    ctx.protected_args holds the subcommand name; ctx.args holds the rest.
    Passing only ctx.args drops the subcommand, so the container shows help.
    """
    config = tmp_path / 'foo.json'
    config.write_text('{}')
    mock_run = mocker.patch('runzi.cli.docker_wrapper.run_in_docker', return_value=0)
    runner.invoke(app, ['--docker', 'hazard', 'oq-hazard', str(config)])
    mock_run.assert_called_once()
    inner_args = mock_run.call_args.args[0]
    assert inner_args[0] == 'hazard', f'subcommand missing from inner_args: {inner_args}'
    assert 'oq-hazard' in inner_args
    assert str(config) in inner_args
