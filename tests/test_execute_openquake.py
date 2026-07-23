"""Tests for the OpenQuake worker-core cap in execute_openquake (#344).

On AWS Batch EC2 the container sees the *host's* cores (CPU shares, not cpuset), so OpenQuake sizes its
processpool to the whole box and OOM-kills a container memory-capped for far fewer vCPU. The fix caps
``[distribution] num_cores`` in the openquake.cfg that ``oq`` reads. These cover the two pure helpers that
do that; the subprocess orchestration and the ``oq`` engine honouring it are verified by a live re-pilot.
"""

import configparser

from runzi.tasks.oq_hazard.execute_openquake import _num_cores_cap, _parse_winning_cfg_path, _set_oq_num_cores

# Real `oq info cfg` output (last path wins); a trailing config dump may follow the path block.
OQ_INFO_CFG = """\
Looking at the following paths (the last wins)
/opt/oq-venv/lib/python3.11/site-packages/openquake/engine/openquake.cfg
/opt/oq-venv/openquake.cfg
/toshi-home/openquake.cfg
"""


class TestParseWinningCfgPath:
    def test_returns_the_last_openquake_cfg_path(self):
        assert str(_parse_winning_cfg_path(OQ_INFO_CFG)) == '/toshi-home/openquake.cfg'

    def test_ignores_a_trailing_config_dump_after_the_paths(self):
        noisy = OQ_INFO_CFG + '\n[distribution]\nnum_cores = 64\n[dbserver]\nport = 1907\n'
        assert str(_parse_winning_cfg_path(noisy)) == '/toshi-home/openquake.cfg'

    def test_none_when_no_cfg_path_present(self):
        assert _parse_winning_cfg_path('some unrelated output\nno paths here') is None


class TestNumCoresCap:
    """The cap is applied ONLY inside AWS Batch — never on a local host, where it would throttle the user
    and persistently rewrite their real openquake.cfg."""

    def test_applies_the_cap_inside_aws_batch(self, monkeypatch):
        monkeypatch.setenv('AWS_BATCH_JOB_ID', 'abc123:0')
        assert _num_cores_cap(8) == 8

    def test_no_cap_on_a_local_host(self, monkeypatch):
        monkeypatch.delenv('AWS_BATCH_JOB_ID', raising=False)
        assert _num_cores_cap(8) is None  # local run: leave OQ (and the user's openquake.cfg) alone

    def test_none_stays_none_even_in_batch(self, monkeypatch):
        monkeypatch.setenv('AWS_BATCH_JOB_ID', 'abc123:0')
        assert _num_cores_cap(None) is None


class TestSetOqNumCores:
    def test_creates_cfg_with_num_cores_when_absent(self, tmp_path):
        cfg = tmp_path / 'openquake.cfg'
        _set_oq_num_cores(cfg, 8)
        parser = configparser.ConfigParser()
        parser.read(cfg)
        assert parser['distribution']['num_cores'] == '8'

    def test_creates_parent_directory_if_missing(self, tmp_path):
        cfg = tmp_path / 'nested' / 'dir' / 'openquake.cfg'
        _set_oq_num_cores(cfg, 4)
        assert cfg.exists()
        parser = configparser.ConfigParser()
        parser.read(cfg)
        assert parser['distribution']['num_cores'] == '4'

    def test_preserves_existing_settings_and_overrides_num_cores(self, tmp_path):
        cfg = tmp_path / 'openquake.cfg'
        cfg.write_text('[dbserver]\nport = 1907\n\n[distribution]\nnum_cores = 64\noq_distribute = processpool\n')
        _set_oq_num_cores(cfg, 16)
        parser = configparser.ConfigParser()
        parser.read(cfg)
        assert parser['distribution']['num_cores'] == '16'  # overridden
        assert parser['distribution']['oq_distribute'] == 'processpool'  # preserved
        assert parser['dbserver']['port'] == '1907'  # other sections preserved
