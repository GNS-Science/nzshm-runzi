"""Tests for the --cluster-mode CLI option."""

import re

import pytest
from typer.testing import CliRunner

from runzi.automation import local_config
from runzi.automation.local_config import ClusterModeEnum
from runzi.cli import runzi_cli
from runzi.cli.runzi_cli import cluster_mode_callback


# some platforms print ANSI codes to the CLI output
def strip_ansi(text: str) -> str:
    return re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', text)


env = {"NO_COLOR": "1", "LANG": "en_US.UTF-8"}
runner = CliRunner(env=env)


# reset default mode before each test
@pytest.fixture(autouse=True)
def reset_cluster_mode():
    local_config.CLUSTER_MODE = ClusterModeEnum.LOCAL


# ── Unit tests for the callback function itself ─────────────────────────────


def test_callback_none_gets_default():
    cluster_mode_callback()
    assert local_config.CLUSTER_MODE is local_config.DEFAULT_CLUSTER_MODE


def test_callback_sets_cluster_mode():
    cluster_mode_callback(ClusterModeEnum.AWS)
    assert local_config.CLUSTER_MODE is ClusterModeEnum.AWS


def test_callback_sets_cluster_mode_cluster():
    cluster_mode_callback(ClusterModeEnum.CLUSTER)
    assert local_config.CLUSTER_MODE is ClusterModeEnum.CLUSTER


def test_callback_default_when_none():
    local_config.CLUSTER_MODE = ClusterModeEnum.CLUSTER  # non-default
    cluster_mode_callback()
    assert local_config.CLUSTER_MODE is local_config.DEFAULT_CLUSTER_MODE  # changed


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
