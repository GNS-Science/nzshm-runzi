"""Tests for the OpenQuake hazard EC2 sizing benchmark scripts (#344).

The scripts live under ``scripts/ec2_sizing/`` (not on the package path), so they're loaded by file
path. Only the side-effect-free grid/render/analysis logic is covered — submit/collect I/O needs live AWS.

OQ hazard runs *to completion*, so the matrix is family x vCPU and the metric is wall-clock time from the
Batch job summary (no Toshi log to parse). On EC2 the container sees the host's cores, so each cell ships
``num_cores = vcpu`` to cap OpenQuake's num_cores (#344); the collector reads back the worker count OQ
logged (``oq_cores``) to confirm the cap took.
"""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / 'scripts' / 'ec2_sizing'


def _load(name: str) -> ModuleType:
    module_name = f'ec2_sizing_{name}'
    spec = importlib.util.spec_from_file_location(module_name, _SCRIPTS / f'{name}.py')
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module  # dataclasses resolves field types via sys.modules at exec time
    spec.loader.exec_module(module)
    return module


submit = _load('submit_oq_hazard_matrix')
collect = _load('collect_oq_hazard_results')


class TestBuildCells:
    def test_full_grid_size_is_families_x_default_vcpus_x_replicates(self):
        cells = submit.build_cells(replicates=2)
        assert len(cells) == len(submit.DEFAULT_FAMILIES) * len(submit.DEFAULT_VCPUS) * 2

    def test_cells_have_no_thread_field(self):
        # OpenQuake auto-parallelises across container vCPUs; there is no thread knob to pin.
        cell = submit.build_cells(1)[0]
        assert not hasattr(cell, 'threads')

    def test_memory_is_vcpu_times_family_ratio(self):
        cell = next(c for c in submit.build_cells(1) if c.family == 'c6a' and c.vcpu == 8)
        assert cell.memory_mb == 8 * submit.FAMILY_MB_PER_VCPU['c6a']

    def test_cell_id_is_unique_per_cell(self):
        cells = submit.build_cells(2)
        assert len({c.cell_id for c in cells}) == len(cells)

    def test_families_filter_selects_only_given_families(self):
        cells = submit.build_cells(1, families=['c6a'])
        assert {c.family for c in cells} == {'c6a'}
        assert len(cells) == len(submit.DEFAULT_VCPUS)

    def test_64_vcpu_is_an_allowed_opt_in_but_not_in_the_default_grid(self):
        assert 64 in submit.VCPUS and 64 not in submit.DEFAULT_VCPUS  # --vcpus 64 accepted; excluded by default
        cells = submit.build_cells(1, families=['c6a'], vcpus=[64])
        assert [c.vcpu for c in cells] == [64]

    def test_vcpus_filter_selects_only_given_vcpus(self):
        cells = submit.build_cells(1, families=['m6a'], vcpus=[8])
        assert [(c.family, c.vcpu) for c in cells] == [('m6a', 8)]


class TestLimit:
    def test_limit_one_dry_run_renders_single_cell(self, capsys):
        rc = submit.main(['--limit', '1', '--dry-run'])
        assert rc == 0
        out = capsys.readouterr().out
        assert 'submitting 1 of 16 cells' in out  # 2 families x 4 vCPU x 2 replicates
        assert out.count('ecs_vcpu') == 1  # exactly one cell rendered

    def test_no_limit_dry_run_renders_full_grid(self, capsys):
        submit.main(['--replicates', '1', '--dry-run'])
        assert 'submitting 8 of 8 cells' in capsys.readouterr().out  # 2 families x 4 vCPU x 1 replicate

    def test_families_flag_shrinks_the_grid(self, capsys):
        submit.main(['--families', 'c6a', '--replicates', '1', '--dry-run'])
        assert 'submitting 4 of 4 cells' in capsys.readouterr().out  # 1 family x 4 vCPU x 1 replicate

    def test_defaults_to_experimental_job_definition(self, capsys):
        submit.main(['--limit', '1', '--dry-run'])
        assert 'runzi-ec2-experimental-JD' in capsys.readouterr().out

    def test_prod_flag_targets_prod_job_definition(self, capsys):
        submit.main(['--limit', '1', '--prod', '--dry-run'])
        assert '"ecs_job_definition": "runzi-ec2-JD"' in capsys.readouterr().out


class TestRenderConfig:
    def _template(self):
        return {'nshm_model_version': 'NSHM_v1.0.4', 'srm_logic_tree': 'srm_single_branch_TEST.json'}

    def test_injects_ec2_sizing_overrides_with_num_cores_pinned_to_vcpu(self):
        cell = submit.Cell(family='c6a', vcpu=16, memory_mb=28800, replicate=0)
        config = submit.render_config(self._template(), cell, 240, 'runzi-ec2-JD')
        overrides = config['submission_arg_overrides']
        assert overrides['ecs_vcpu'] == 16
        # num_cores carries the OQ core budget -> openquake.cfg num_cores; must equal vCPU or OQ grabs
        # all host cores on EC2 and OOMs the container (#344).
        assert overrides['num_cores'] == 16
        assert overrides['ecs_memory'] == 28800
        assert overrides['ecs_job_definition'] == 'runzi-ec2-JD'
        assert overrides['ecs_max_job_time_min'] == 240

    def test_leaves_template_untouched(self):
        template = self._template()
        cell = submit.Cell(family='c6a', vcpu=4, memory_mb=7200, replicate=0)
        submit.render_config(template, cell, 240, 'runzi-ec2-experimental-JD')
        assert 'submission_arg_overrides' not in template  # deep-copied, not mutated in place

    def test_queue_prefix_routes_to_pinned_family_queue(self):
        cell = submit.Cell(family='m6a', vcpu=8, memory_mb=30400, replicate=0)
        config = submit.render_config(
            self._template(), cell, 240, 'runzi-ec2-experimental-JD', queue_prefix='ec2sizing'
        )
        assert config['submission_arg_overrides']['ecs_job_queue'] == 'ec2sizing-m6a-Q'

    def test_no_job_queue_override_by_default(self):
        cell = submit.Cell(family='c6a', vcpu=8, memory_mb=14400, replicate=0)
        config = submit.render_config(self._template(), cell, 240, 'runzi-ec2-experimental-JD')
        assert 'ecs_job_queue' not in config['submission_arg_overrides']  # queue derives from the JD


class TestTemplate:
    def test_template_is_valid_json_for_a_single_srm_branch_hazard_job(self):
        template = json.loads((_SCRIPTS / 'oq_hazard.template.json').read_text())
        assert template['nshm_model_version']  # full 2022 GMCM comes from the model version
        # A single-branch SRM co-located with the template -> the runner explodes it into exactly one job.
        srm = template['srm_logic_tree']
        assert (_SCRIPTS / srm).exists(), 'single-branch SRM must sit next to the template so it resolves'
        assert template['imts'] and template['imtls'] and template['locations']


class TestOqWorkerCount:
    """OpenQuake logs ``Using N processpool workers`` — the ground truth that the num_cores cap took (#344)."""

    def test_parses_the_worker_count_from_a_log_line(self):
        lines = ['INFO:root:Using engine version 3.23.4', 'WARNING:root:Using 8 processpool workers', 'more']
        assert collect.parse_oq_worker_count(lines) == 8

    def test_returns_the_first_match_and_stops(self):
        # A generator that would blow up if consumed past the match proves we stop early (cheap log read).
        def _lines():
            yield 'WARNING:root:Using 16 processpool workers'
            raise AssertionError('must stop iterating at the first match')

        assert collect.parse_oq_worker_count(_lines()) == 16

    def test_none_when_absent(self):
        assert collect.parse_oq_worker_count(['no worker line here', 'still none']) is None


class TestCollectRows:
    @pytest.fixture(autouse=True)
    def _default_no_logs(self, monkeypatch):
        # Default: no CloudWatch logs, so oq_cores is None and tests never touch AWS. Tests that care about
        # the worker-count check override collect.job_log_events themselves.
        monkeypatch.setattr(collect, 'job_log_events', lambda job_id: iter(()))

    def test_captures_oq_worker_count_from_the_job_log(self, monkeypatch):
        self._patch_batch(monkeypatch)
        monkeypatch.setattr(
            collect, 'job_log_events', lambda job_id: iter(['WARNING:root:Using 8 processpool workers'])
        )
        row = collect.collect_rows(self._manifest())[0]
        assert row['oq_cores'] == 8  # matches the cell's 8 vCPU -> the cap took

    def test_records_a_worker_count_mismatch(self, monkeypatch):
        # The cap silently didn't take: OQ used the host's cores. The row must carry the observed count so
        # the summary can flag the (now invalid) wall time.
        self._patch_batch(monkeypatch)
        monkeypatch.setattr(collect, 'job_log_events', lambda job_id: iter(['Using 64 processpool workers']))
        row = collect.collect_rows(self._manifest())[0]  # cell is 8 vCPU
        assert row['oq_cores'] == 64

    def test_oq_cores_none_when_log_unavailable(self, monkeypatch):
        self._patch_batch(monkeypatch)

        def _no_stream(job_id):
            raise collect.LogStreamNotAvailable(job_id)

        monkeypatch.setattr(collect, 'job_log_events', _no_stream)
        row = collect.collect_rows(self._manifest())[0]
        assert row['oq_cores'] is None  # graceful: a missing/aged log doesn't break collection

    def _manifest(self, job_queue: str | None = 'ec2sizing-c6a-Q'):
        return {
            'rows': [
                {
                    'general_task_id': 'gt1',
                    'cell_id': 'c6a-v8-r0',
                    'family': 'c6a',
                    'vcpu': 8,
                    'memory_mb': 14400,
                    'replicate': 0,
                    'job_queue': job_queue,
                }
            ]
        }

    def _patch_batch(self, monkeypatch, instance: str | None = 'c6a.2xlarge', status='SUCCEEDED'):
        monkeypatch.setattr(
            collect,
            'jobs_for_general_task',
            lambda gt_id, queues=None: [
                {'jobId': 'j1', 'status': status, 'startedAt': 1_000_000, 'stoppedAt': 1_600_000}
            ],
        )
        monkeypatch.setattr(collect, 'instance_type_by_job_id', lambda job_ids: {'j1': instance} if instance else {})

    def test_builds_duration_and_cost_from_batch_no_toshi(self, monkeypatch):
        self._patch_batch(monkeypatch)
        rows = collect.collect_rows(self._manifest())
        assert len(rows) == 1
        row = rows[0]
        assert row['instance_type'] == 'c6a.2xlarge'
        assert row['duration_sec'] == 600.0
        assert 'threads' not in row  # OQ rows carry no thread column
        assert row['cost_usd'] is not None  # priced from the fair-share formula

    def test_pinned_run_is_priced_from_family_when_ecs_lookup_fails(self, monkeypatch):
        # CE scaled to zero (or no ECS perms) -> read-back is empty/denied, but a pinned cell's instance
        # is derived from family + vCPU, so cost still computes. This is the real-run failure mode.
        from botocore.exceptions import ClientError

        monkeypatch.setattr(
            collect,
            'jobs_for_general_task',
            lambda gt_id, queues=None: [
                {'jobId': 'j1', 'status': 'SUCCEEDED', 'startedAt': 1_000_000, 'stoppedAt': 1_600_000}
            ],
        )

        def _deny(job_ids):
            raise ClientError(
                {'Error': {'Code': 'AccessDeniedException', 'Message': 'no'}}, 'DescribeContainerInstances'
            )

        monkeypatch.setattr(collect, 'instance_type_by_job_id', _deny)
        row = collect.collect_rows(self._manifest())[0]  # c6a, 8 vCPU, pinned to ec2sizing-c6a-Q
        assert row['instance_type'] == 'c6a.2xlarge'  # derived from family + vCPU, no read-back
        assert row['cost_usd'] is not None
        assert row['duration_sec'] == 600.0

    def test_unpinned_cell_is_not_priced_from_family(self, monkeypatch):
        # Without a per-family queue the instance is whatever "optimal" picked, so we must NOT assume the
        # family. Unresolved read-back -> no instance, no cost.
        self._patch_batch(monkeypatch, instance=None)
        row = collect.collect_rows(self._manifest(job_queue=None))[0]
        assert row['instance_type'] is None and row['cost_usd'] is None
        assert row['duration_sec'] == 600.0  # duration still reported

    def test_instance_type_override_prices_without_ecs_lookup(self, monkeypatch):
        monkeypatch.setattr(
            collect,
            'jobs_for_general_task',
            lambda gt_id, queues=None: [
                {'jobId': 'j1', 'status': 'SUCCEEDED', 'startedAt': 1_000_000, 'stoppedAt': 1_600_000}
            ],
        )

        def _boom(job_ids):
            raise AssertionError('instance_type_by_job_id must not be called when overridden')

        monkeypatch.setattr(collect, 'instance_type_by_job_id', _boom)
        row = collect.collect_rows(self._manifest(), instance_type_override='c6a.4xlarge')[0]
        assert row['instance_type'] == 'c6a.4xlarge'
        assert row['cost_usd'] is not None  # priced despite no ECS lookup

    def test_searches_the_given_queues(self, monkeypatch):
        seen = {}

        def _jobs(gt_id, queues=None):
            seen['queues'] = queues
            return []

        monkeypatch.setattr(collect, 'jobs_for_general_task', _jobs)
        monkeypatch.setattr(collect, 'instance_type_by_job_id', lambda job_ids: {})
        collect.collect_rows(self._manifest(), queues=('ec2sizing-c6a-Q',))
        assert seen['queues'] == ('ec2sizing-c6a-Q',)

    def test_missing_job_survives_with_none_duration_and_cost(self, monkeypatch):
        monkeypatch.setattr(collect, 'jobs_for_general_task', lambda gt_id, queues=None: [])
        monkeypatch.setattr(collect, 'instance_type_by_job_id', lambda job_ids: {})
        row = collect.collect_rows(self._manifest())[0]
        assert row['duration_sec'] is None and row['cost_usd'] is None and row['status'] is None
        assert row['cell_id'] == 'c6a-v8-r0'  # row still produced


class TestExpectedInstanceType:
    def test_maps_family_and_vcpu_to_exact_fit_size(self):
        assert collect.expected_instance_type('c6a', 8) == 'c6a.2xlarge'
        assert collect.expected_instance_type('m6a', 32) == 'm6a.8xlarge'
        assert collect.expected_instance_type('c6a', 4) == 'c6a.xlarge'

    def test_none_for_missing_family_or_unmapped_vcpu(self):
        assert collect.expected_instance_type(None, 8) is None
        assert collect.expected_instance_type('c6a', 7) is None  # not an exact-fit size

    def test_none_when_derived_type_not_in_price_table(self):
        assert collect.expected_instance_type('z9z', 8) is None  # unknown family -> not priced


class TestCostPrimitives:
    """The shared _cost.py primitives, re-exposed on the collector module."""

    def test_duration_is_stopped_minus_started(self):
        assert collect.duration_seconds({'startedAt': 1_000_000, 'stoppedAt': 1_600_000}) == 600.0

    def test_duration_missing_timestamp_is_none(self):
        assert collect.duration_seconds({'startedAt': 1_000_000}) is None

    def test_fair_share_cost_is_per_vcpu_prorated(self):
        # c6a.2xlarge: 8 vCPU, $0.306/hr. A 8-vCPU job for 1 hour = the full instance-hour.
        assert collect.job_cost_usd('c6a.2xlarge', job_vcpu=8, seconds=3600.0) == round(0.306, 10)

    def test_unknown_instance_type_is_none(self):
        assert collect.job_cost_usd('t3.nano', 2, 3600.0) is None
