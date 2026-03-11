"""Tests for the --cluster-mode CLI option."""

import re

import pytest
from typer.testing import CliRunner

from runzi.automation import local_config
from runzi.automation.local_config import ClusterModeEnum
from runzi.cli import (
    cluster_mode_callback,
    hazard_cli,
    inversion_cli,
    inversion_post_process_cli,
    reports_cli,
    runzi_cli,
    rupture_sets_cli,
)


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
    assert local_config.CLUSTER_MODE is ClusterModeEnum.LOCAL


def test_callback_sets_cluster_mode():
    cluster_mode_callback(ClusterModeEnum.AWS)
    assert local_config.CLUSTER_MODE is ClusterModeEnum.AWS


def test_callback_sets_cluster_mode_cluster():
    cluster_mode_callback(ClusterModeEnum.CLUSTER)
    assert local_config.CLUSTER_MODE is ClusterModeEnum.CLUSTER


def test_callback_noop_when_none():
    local_config.CLUSTER_MODE = ClusterModeEnum.CLUSTER  # non-default
    cluster_mode_callback()
    assert local_config.CLUSTER_MODE is ClusterModeEnum.CLUSTER  # unchanged


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
    assert local_config.CLUSTER_MODE is ClusterModeEnum.LOCAL


def test_root_cli_help_shows_cluster_mode():
    result = runner.invoke(runzi_cli.app, ['--help'])
    assert '--cluster-mode' in strip_ansi(result.output)


# ── Sub-CLI parametrized tests ───────────────────────────────────────────────
# Each tuple: (app, first_subcommand_name, cli_label)

SUB_CLIS = [
    (hazard_cli.app, 'oq-hazard', 'hazard'),
    (inversion_cli.app, 'crustal', 'inversion'),
    (inversion_post_process_cli.app, 'avg-sol', 'ipp'),
    (reports_cli.app, 'rupset', 'reports'),
    (rupture_sets_cli.app, 'coulomb', 'rupset'),
]


@pytest.mark.parametrize('app,subcmd,label', SUB_CLIS)
def test_sub_cli_cluster_mode_sets_aws(app, subcmd, label):
    result = runner.invoke(app, ['--cluster-mode', 'AWS', subcmd, '--help'])
    assert result.exit_code == 0, f'{label}: {result.output}'
    assert local_config.CLUSTER_MODE is ClusterModeEnum.AWS


@pytest.mark.parametrize('app,subcmd,label', SUB_CLIS)
def test_sub_cli_cluster_mode_sets_cluster(app, subcmd, label):
    result = runner.invoke(app, ['--cluster-mode', 'CLUSTER', subcmd, '--help'])
    assert result.exit_code == 0, f'{label}: {result.output}'
    assert local_config.CLUSTER_MODE is ClusterModeEnum.CLUSTER


@pytest.mark.parametrize('app,subcmd,label', SUB_CLIS)
def test_sub_cli_no_option_keeps_default(app, subcmd, label):
    result = runner.invoke(app, [subcmd, '--help'])
    assert result.exit_code == 0, f'{label}: {result.output}'
    assert local_config.CLUSTER_MODE is ClusterModeEnum.LOCAL


@pytest.mark.parametrize('app,subcmd,label', SUB_CLIS)
def test_sub_cli_help_shows_cluster_mode(app, subcmd, label):
    result = runner.invoke(app, ['--help'])
    assert '--cluster-mode' in strip_ansi(result.output), f'{label} missing --cluster-mode in help'
