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


def test_build_tasks_uses_runtime_use_api(monkeypatch):
    """The TaskRuntimeArgs shipped to the worker must carry the runtime local_config.USE_API, not an
    import-time snapshot (use_api is set fresh in build_tasks, ADR-0009)."""
    from unittest.mock import MagicMock, patch

    from runzi import build_tasks as bt
    from runzi.arguments import SubmissionArgs, TaskLanguage
    from runzi.automation.local_config import ClusterModeEnum
    from runzi.automation.toshi_api import ModelType

    monkeypatch.setattr(bt.local_config, 'USE_API', True)
    monkeypatch.setattr(bt.local_config, 'CLUSTER_MODE', ClusterModeEnum.AWS)

    submission_args = SubmissionArgs(
        task_language=TaskLanguage.PYTHON, ecs_max_job_time_min=30, ecs_memory=1024, ecs_vcpu=1
    )

    mock_sweeper = MagicMock()
    mock_sweeper.get_tasks.return_value = [MagicMock()]
    mock_module = MagicMock()
    mock_module.__name__ = 'runzi.tasks.example'

    fake_factory = MagicMock()
    fake_factory.get_container_task.return_value = 'run.sh'
    fake_factory_class = MagicMock()
    fake_factory_class.create.return_value = fake_factory

    captured = {}

    def _capture(**kwargs):
        captured.update(kwargs)
        return {}

    with (
        patch.object(bt, 'get_factory', return_value=fake_factory_class),
        patch.object(bt, 'resolve_job_definition_digest', return_value='sha256:x'),
        patch.object(bt, 'get_ecs_job_config', side_effect=_capture),
    ):
        list(bt.build_tasks(mock_sweeper, submission_args, mock_module, ModelType.CRUSTAL, 'job'))

    assert captured['task_runtime_args'].use_api is True
