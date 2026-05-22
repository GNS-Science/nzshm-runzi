"""Tests for the --cluster-mode CLI option."""

import re

import pytest
from typer.testing import CliRunner

from runzi.automation import local_config
from runzi.automation.local_config import ClusterModeEnum
from runzi.cli import runzi_cli


# some platforms print ANSI codes to the CLI output
def strip_ansi(text: str) -> str:
    return re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', text)


env = {"NO_COLOR": "1", "LANG": "en_US.UTF-8"}
runner = CliRunner(env=env)


# reset default mode and USE_API before each test
@pytest.fixture(autouse=True)
def reset_cluster_mode():
    saved_mode = local_config.CLUSTER_MODE
    saved_use_api = local_config.USE_API
    local_config.CLUSTER_MODE = ClusterModeEnum.LOCAL
    yield
    local_config.CLUSTER_MODE = saved_mode
    local_config.USE_API = saved_use_api


# ── Root CLI tests ───────────────────────────────────────────────────────────


def test_root_cli_cluster_mode_sets_aws():
    result = runner.invoke(runzi_cli.app, ['--cluster-mode', 'AWS', 'hazard', 'oq-hazard', '--help'])
    assert result.exit_code == 0
    assert local_config.CLUSTER_MODE is ClusterModeEnum.AWS


def test_root_cli_cluster_mode_sets_cluster():
    result = runner.invoke(runzi_cli.app, ['--cluster-mode', 'CLUSTER', 'hazard', 'oq-hazard', '--help'])
    assert result.exit_code == 0
    assert local_config.CLUSTER_MODE is ClusterModeEnum.CLUSTER


def test_root_cli_no_option_keeps_default():
    result = runner.invoke(runzi_cli.app, ['hazard', 'oq-hazard', '--help'])
    assert result.exit_code == 0
    assert local_config.CLUSTER_MODE is local_config.DEFAULT_CLUSTER_MODE


def test_root_cli_help_shows_cluster_mode():
    result = runner.invoke(runzi_cli.app, ['--help'])
    assert '--cluster-mode' in strip_ansi(result.output)


def test_aws_cluster_mode_forces_use_api():
    """AWS mode must set USE_API=True regardless of env var."""
    result = runner.invoke(runzi_cli.app, ['--cluster-mode', 'AWS', 'hazard', 'oq-hazard', '--help'])
    assert result.exit_code == 0
    assert local_config.USE_API is True


def test_non_aws_cluster_mode_does_not_change_use_api():
    """LOCAL and CLUSTER modes must not override USE_API."""
    original = local_config.USE_API
    result = runner.invoke(runzi_cli.app, ['--cluster-mode', 'LOCAL', 'hazard', 'oq-hazard', '--help'])
    assert result.exit_code == 0
    assert local_config.USE_API == original


def test_set_system_args_uses_runtime_use_api(monkeypatch):
    """set_system_args must reflect local_config.USE_API, not the import-time snapshot."""
    from unittest.mock import MagicMock

    from runzi.arguments import SystemArgs, TaskLanguage
    from runzi.automation.toshi_api import ModelType, SubtaskType
    from runzi.job_runner import JobRunner

    monkeypatch.setattr(local_config, 'USE_API', True)

    baked_in_sys_args = SystemArgs(
        task_language=TaskLanguage.PYTHON,
        use_api=False,
        ecs_max_job_time_min=30,
        ecs_memory=1024,
        ecs_vcpu=1,
        ecs_job_definition='test-job-def',
        ecs_job_queue='test-queue',
    )
    mock_module = MagicMock()
    mock_module.default_system_args = baked_in_sys_args
    mock_sweeper = MagicMock()
    mock_sweeper.sys_arg_overrides = {}

    class ConcreteRunner(JobRunner):
        subtask_type = SubtaskType.INVERSION
        job_name = 'test'

        def get_model_type(self):
            return ModelType.CRUSTAL

    result = ConcreteRunner(mock_sweeper, mock_module).set_system_args()
    assert result.use_api is True
