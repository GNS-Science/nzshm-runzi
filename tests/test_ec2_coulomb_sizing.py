"""Tests for the coulomb rupture-set EC2 sizing benchmark scripts (#323).

The scripts live under ``scripts/ec2_sizing/`` (not on the package path), so they're loaded by file
path. Only the side-effect-free grid/render/analysis logic is covered — submit/collect I/O needs live AWS.
The metric here is wall-clock time (from the Batch job summary), so there is no Toshi log to parse.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_SCRIPTS = Path(__file__).resolve().parent.parent / 'scripts' / 'ec2_sizing'


def _load(name: str) -> ModuleType:
    module_name = f'ec2_sizing_{name}'
    spec = importlib.util.spec_from_file_location(module_name, _SCRIPTS / f'{name}.py')
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module  # dataclasses resolves field types via sys.modules at exec time
    spec.loader.exec_module(module)
    return module


submit = _load('submit_coulomb_matrix')
collect = _load('collect_coulomb_results')


class TestBuildCells:
    def test_full_grid_size_is_families_x_vcpus_x_replicates(self):
        cells = submit.build_cells(replicates=2)
        assert len(cells) == len(submit.DEFAULT_FAMILIES) * len(submit.VCPUS) * 2

    def test_threads_are_pinned_to_vcpu(self):
        assert all(c.threads == c.vcpu for c in submit.build_cells(1))

    def test_memory_is_vcpu_times_family_ratio(self):
        cell = next(c for c in submit.build_cells(1) if c.family == 'c6a' and c.vcpu == 8)
        assert cell.memory_mb == 8 * submit.FAMILY_MB_PER_VCPU['c6a']

    def test_cell_id_is_unique_per_cell(self):
        cells = submit.build_cells(2)
        assert len({c.cell_id for c in cells}) == len(cells)

    def test_families_filter_selects_only_given_families(self):
        cells = submit.build_cells(1, families=['c6a'])
        assert {c.family for c in cells} == {'c6a'}
        assert len(cells) == len(submit.VCPUS)

    def test_vcpus_filter_selects_only_given_vcpus(self):
        cells = submit.build_cells(1, families=['m6a'], vcpus=[8])
        assert [(c.family, c.vcpu) for c in cells] == [('m6a', 8)]


class TestLimit:
    def test_limit_one_dry_run_renders_single_cell(self, capsys):
        rc = submit.main(['--limit', '1', '--dry-run'])
        assert rc == 0
        out = capsys.readouterr().out
        assert 'submitting 1 of 20 cells' in out  # 2 families x 5 vCPU x 2 replicates
        assert out.count('ecs_vcpu') == 1  # exactly one cell rendered

    def test_no_limit_dry_run_renders_full_grid(self, capsys):
        submit.main(['--replicates', '1', '--dry-run'])
        assert 'submitting 10 of 10 cells' in capsys.readouterr().out  # 2 families x 5 vCPU x 1 replicate

    def test_families_flag_shrinks_the_grid(self, capsys):
        submit.main(['--families', 'c6a', '--replicates', '1', '--dry-run'])
        assert 'submitting 5 of 5 cells' in capsys.readouterr().out  # 1 family x 5 vCPU x 1 replicate

    def test_defaults_to_experimental_job_definition(self, capsys):
        submit.main(['--limit', '1', '--dry-run'])
        assert 'runzi-ec2-experimental-JD' in capsys.readouterr().out

    def test_prod_flag_targets_prod_job_definition(self, capsys):
        submit.main(['--limit', '1', '--prod', '--dry-run'])
        assert '"ecs_job_definition": "runzi-ec2-JD"' in capsys.readouterr().out


class TestRenderConfig:
    def _template(self):
        return {'max_sections': 2000, 'fault_model': 'CFM_1_0A_DOM_SANSTVZ'}

    def test_injects_ec2_sizing_overrides_with_threads_pinned_to_vcpu(self):
        cell = submit.Cell(family='c6a', vcpu=16, memory_mb=28800, replicate=0)
        config = submit.render_config(self._template(), cell, 90, 'runzi-ec2-JD')
        overrides = config['submission_arg_overrides']
        assert overrides['ecs_vcpu'] == 16
        assert overrides['java_threads'] == 16  # pinned to vCPU
        assert overrides['ecs_memory'] == 28800
        assert overrides['ecs_job_definition'] == 'runzi-ec2-JD'
        assert overrides['ecs_max_job_time_min'] == 90

    def test_leaves_template_untouched(self):
        template = self._template()
        cell = submit.Cell(family='c6a', vcpu=4, memory_mb=7200, replicate=0)
        submit.render_config(template, cell, 90, 'runzi-ec2-experimental-JD')
        assert 'submission_arg_overrides' not in template  # deep-copied, not mutated in place

    def test_queue_prefix_routes_to_pinned_family_queue(self):
        cell = submit.Cell(family='m6a', vcpu=8, memory_mb=30400, replicate=0)
        config = submit.render_config(self._template(), cell, 90, 'runzi-ec2-experimental-JD', queue_prefix='ec2sizing')
        assert config['submission_arg_overrides']['ecs_job_queue'] == 'ec2sizing-m6a-Q'

    def test_no_job_queue_override_by_default(self):
        cell = submit.Cell(family='c6a', vcpu=8, memory_mb=14400, replicate=0)
        config = submit.render_config(self._template(), cell, 90, 'runzi-ec2-experimental-JD')
        assert 'ecs_job_queue' not in config['submission_arg_overrides']  # queue derives from the JD


class TestCollectRows:
    def _manifest(self, job_queue: str | None = 'ec2sizing-c6a-Q'):
        return {
            'rows': [
                {
                    'general_task_id': 'gt1',
                    'cell_id': 'c6a-v8-r0',
                    'family': 'c6a',
                    'vcpu': 8,
                    'threads': 8,
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
        assert row['threads'] == 8
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
        assert collect.expected_instance_type('m6a', 64) == 'm6a.16xlarge'
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
