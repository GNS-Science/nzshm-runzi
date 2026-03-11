"""Tests for the --cluster-mode CLI option."""

import pytest
from typer.testing import CliRunner

from runzi.automation import local_config
from runzi.automation.local_config import EnvMode
from runzi.cli import (
    cluster_mode_callback,
    hazard_cli,
    inversion_cli,
    inversion_post_process_cli,
    reports_cli,
    runzi_cli,
    rupture_sets_cli,
)
env = {"NO_COLOR": "1"}
runner = CliRunner(env=env)


# reset default mode before each test
@pytest.fixture(autouse=True)
def reset_cluster_mode():
    local_config.CLUSTER_MODE = EnvMode.LOCAL


# ── Unit tests for the callback function itself ─────────────────────────────


def test_callback_none_gets_default():
    cluster_mode_callback()
    assert local_config.CLUSTER_MODE == EnvMode.LOCAL


def test_callback_sets_cluster_mode():
    cluster_mode_callback(EnvMode.AWS)
    assert local_config.CLUSTER_MODE == EnvMode.AWS


def test_callback_sets_cluster_mode_cluster():
    cluster_mode_callback(EnvMode.CLUSTER)
    assert local_config.CLUSTER_MODE == EnvMode.CLUSTER


def test_callback_noop_when_none():
    local_config.CLUSTER_MODE = EnvMode.CLUSTER  # non-default
    cluster_mode_callback()
    assert local_config.CLUSTER_MODE == EnvMode.CLUSTER  # unchanged


# ── Root CLI tests ───────────────────────────────────────────────────────────


def test_root_cli_cluster_mode_sets_aws():
    result = runner.invoke(runzi_cli.app, ['--cluster-mode', 'AWS', 'hazard', 'oq-hazard', '--help'])
    assert result.exit_code == 0
    assert local_config.CLUSTER_MODE == EnvMode.AWS


def test_root_cli_cluster_mode_sets_cluster():
    result = runner.invoke(runzi_cli.app, ['--cluster-mode', 'CLUSTER', 'hazard', 'oq-hazard', '--help'])
    assert result.exit_code == 0
    assert local_config.CLUSTER_MODE == EnvMode.CLUSTER


def test_root_cli_no_option_keeps_default():
    result = runner.invoke(runzi_cli.app, ['hazard', 'oq-hazard', '--help'])
    assert result.exit_code == 0
    assert local_config.CLUSTER_MODE == EnvMode.LOCAL


def test_root_cli_help_shows_cluster_mode():
    result = runner.invoke(runzi_cli.app, ['--help'], env=env)
    assert '--cluster-mode' in result.output


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
    assert local_config.CLUSTER_MODE == EnvMode.AWS


@pytest.mark.parametrize('app,subcmd,label', SUB_CLIS)
def test_sub_cli_cluster_mode_sets_cluster(app, subcmd, label):
    result = runner.invoke(app, ['--cluster-mode', 'CLUSTER', subcmd, '--help'])
    assert result.exit_code == 0, f'{label}: {result.output}'
    assert local_config.CLUSTER_MODE == EnvMode.CLUSTER


@pytest.mark.parametrize('app,subcmd,label', SUB_CLIS)
def test_sub_cli_no_option_keeps_default(app, subcmd, label):
    result = runner.invoke(app, [subcmd, '--help'])
    assert result.exit_code == 0, f'{label}: {result.output}'
    assert local_config.CLUSTER_MODE == EnvMode.LOCAL


@pytest.mark.parametrize('app,subcmd,label', SUB_CLIS)
def test_sub_cli_help_shows_cluster_mode(app, subcmd, label):
    result = runner.invoke(app, ['--help'], env=env)
    assert '--cluster-mode' in result.output, f'{label} missing --cluster-mode in help'
