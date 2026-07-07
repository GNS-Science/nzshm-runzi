"""Tests for the EC2 sizing benchmark scripts (#323): pure grid/render and analysis logic.

The scripts live under ``scripts/ec2_sizing/`` (not on the package path), so they're loaded by file
path. Only the side-effect-free functions are covered — submit/collect I/O needs live AWS.
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


submit = _load('submit_matrix')
collect = _load('collect_results')


class TestBuildCells:
    def test_full_grid_size_is_vcpus_x_ratios_x_replicates(self):
        cells = submit.build_cells(replicates=3)
        assert len(cells) == len(submit.VCPUS) * len(submit.RATIOS_MB_PER_VCPU) * 3

    def test_memory_is_vcpu_times_ratio(self):
        cell = next(c for c in submit.build_cells(1) if c.vcpu == 8 and c.ratio_label == 'M')
        assert cell.memory_mb == 8 * submit.RATIOS_MB_PER_VCPU['M']

    def test_cell_id_is_unique_per_cell(self):
        cells = submit.build_cells(3)
        assert len({c.cell_id for c in cells}) == len(cells)

    def test_ratios_filter_selects_only_given_ratios(self):
        cells = submit.build_cells(1, ratios=['C', 'M'])
        assert len(cells) == len(submit.VCPUS) * 2
        assert {c.ratio_label for c in cells} == {'C', 'M'}


class TestLimit:
    def test_limit_one_dry_run_renders_single_cell(self, capsys):
        rc = submit.main(['--limit', '1', '--dry-run'])
        assert rc == 0
        out = capsys.readouterr().out
        assert 'submitting 1 of 27 cells' in out  # default 3 replicates -> 27-cell grid
        assert out.count('ecs_vcpu') == 1  # exactly one cell rendered

    def test_no_limit_dry_run_renders_full_grid(self, capsys):
        submit.main(['--replicates', '1', '--dry-run'])
        out = capsys.readouterr().out
        assert 'submitting 9 of 9 cells' in out

    def test_ratios_flag_shrinks_the_grid(self, capsys):
        submit.main(['--ratios', 'C', 'M', '--replicates', '1', '--dry-run'])
        assert 'submitting 6 of 6 cells' in capsys.readouterr().out  # 3 vCPU x 2 ratios x 1 replicate

    def test_defaults_to_experimental_job_definition(self, capsys):
        submit.main(['--limit', '1', '--dry-run'])
        assert 'runzi-ec2-experimental-JD' in capsys.readouterr().out

    def test_prod_flag_targets_prod_job_definition(self, capsys):
        submit.main(['--limit', '1', '--prod', '--dry-run'])
        out = capsys.readouterr().out
        assert '"ecs_job_definition": "runzi-ec2-JD"' in out


class TestRenderConfig:
    def _template(self):
        return {'rupture_set': {'rupture_set_id': 'RmlsZToxMDAwNjk='}, 'max_inversion_time': 10.0}

    def test_injects_ec2_sizing_overrides(self):
        cell = submit.Cell(vcpu=8, memory_mb=32768, ratio_label='M', replicate=0)
        config = submit.render_config(self._template(), cell, None, 30, 'runzi-ec2-JD')
        overrides = config['submission_arg_overrides']
        assert overrides['ecs_vcpu'] == 8
        assert overrides['ecs_memory'] == 32768
        assert overrides['ecs_job_definition'] == 'runzi-ec2-JD'  # queue + compute env derive from this
        assert overrides['ecs_max_job_time_min'] == 30

    def test_leaves_template_untouched(self):
        template = self._template()
        cell = submit.Cell(vcpu=4, memory_mb=8192, ratio_label='C', replicate=0)
        submit.render_config(template, cell, None, 30, 'runzi-ec2-experimental-JD')
        assert 'submission_arg_overrides' not in template  # deep-copied, not mutated in place

    def test_max_inversion_time_override_applied(self):
        cell = submit.Cell(vcpu=4, memory_mb=8192, ratio_label='C', replicate=0)
        config = submit.render_config(self._template(), cell, 2.0, 30, 'runzi-ec2-experimental-JD')
        assert config['max_inversion_time'] == 2.0


# Real java_app.<port>.log lines from a crustal inversion.
SAMPLE_LOG = [
    'Total Iterations: 30388979',
    'Total Perturbations: 1996244',
    'Best energy:',
    '    Total:    3631.1384    UncertSlipRate:    1992.0752    RateMinimize:    0.11432464',
    '    UncertMFDEquality:    573.1812    PaleoRate:    1057.84    LaplaceSmooth:    7.927568',
]


class TestParseMaxInt:
    def test_reads_total_iterations_line(self):
        assert collect.parse_max_int(SAMPLE_LOG, collect.DEFAULT_ITERATION_REGEX) == 30388979

    def test_iterations_regex_does_not_capture_perturbations_or_energy_total(self):
        # 'Total Perturbations:' and the energy block's 'Total:' must not be mistaken for iterations.
        assert collect.parse_max_int(SAMPLE_LOG[1:], collect.DEFAULT_ITERATION_REGEX) is None

    def test_reads_total_perturbations_line(self):
        assert collect.parse_max_int(SAMPLE_LOG, collect.PERTURBATIONS_REGEX) == 1996244

    def test_takes_max_across_repeated_progress_lines(self):
        lines = ['Total Iterations: 100', 'Total Iterations: 30388979']
        assert collect.parse_max_int(lines, collect.DEFAULT_ITERATION_REGEX) == 30388979

    def test_tolerates_thousands_separators(self):
        assert collect.parse_max_int(['Total Iterations: 1,234,567'], collect.DEFAULT_ITERATION_REGEX) == 1234567

    def test_returns_none_when_nothing_matches(self):
        assert collect.parse_max_int(['no counts here', 'just text'], collect.DEFAULT_ITERATION_REGEX) is None

    def test_custom_pattern(self):
        assert collect.parse_max_int(['STEP=42 done'], r'STEP=(\d+)') == 42

    def test_comma_only_capture_is_skipped_not_crashed(self):
        # A loose pattern that captures only a comma must be skipped, not raise ValueError.
        assert collect.parse_max_int(['Total Iterations: ,'], r'(?i)total\s+iterations[^0-9]*([0-9,]+)') is None


class TestParseFinalEnergy:
    def test_reads_total_from_best_energy_block(self):
        assert collect.parse_final_energy(SAMPLE_LOG) == 3631.1384

    def test_returns_none_without_best_energy_block(self):
        assert collect.parse_final_energy(['Total Iterations: 5', 'nothing here']) is None

    def test_takes_last_block(self):
        lines = ['Best energy:', '    Total:    9999.0', 'Best energy:', '    Total:    3631.1384']
        assert collect.parse_final_energy(lines) == 3631.1384

    def test_does_not_confuse_total_iterations_for_energy(self):
        # 'Total Iterations:' is not a 'Total:' energy line, and there's no Best energy header.
        assert collect.parse_final_energy(['Total Iterations: 30388979']) is None


def _subtasks_with_java_log(file_id='F1', file_name='java_app.26533.log'):
    """Shape returned by ToshiApi.get_general_task_subtask_files, with one java_app log file."""
    return {
        'children': {
            'edges': [
                {
                    'node': {
                        'child': {
                            'id': 'child1',
                            'files': {'edges': [{'node': {'file': {'id': file_id, 'file_name': file_name}}}]},
                        }
                    }
                }
            ]
        }
    }


class _FakeToshiFile:
    def __init__(self, contents_by_id):
        self._contents = contents_by_id

    def download_file(self, file_id, target_dir, target_name=None):
        path = Path(target_dir) / f'{file_id}.log'
        path.write_text(self._contents[file_id])
        return str(path)


class _FakeToshiApi:
    def __init__(self, subtasks_by_gt, file_contents=None, error=None):
        self._subtasks_by_gt = subtasks_by_gt
        self._error = error
        self.file = _FakeToshiFile(file_contents or {})

    def get_general_task_subtask_files(self, gt_id):
        if self._error is not None:
            raise self._error
        return self._subtasks_by_gt[gt_id]


class TestJavaLogFileId:
    def test_finds_java_app_log(self):
        assert collect.java_log_file_id(_subtasks_with_java_log('F9')) == 'F9'

    def test_ignores_non_java_logs(self):
        resp = {
            'children': {
                'edges': [
                    {
                        'node': {
                            'child': {
                                'files': {
                                    'edges': [
                                        {'node': {'file': {'id': 'A', 'file_name': 'python_script.1.log'}}},
                                        {'node': {'file': {'id': 'B', 'file_name': 'solution.zip'}}},
                                    ]
                                }
                            }
                        }
                    }
                ]
            }
        }
        assert collect.java_log_file_id(resp) is None

    def test_empty_or_missing_children(self):
        assert collect.java_log_file_id({'children': {'edges': []}}) is None
        assert collect.java_log_file_id({}) is None


class TestCollectRows:
    def _manifest(self):
        return {
            'rows': [
                {
                    'general_task_id': 'gt1',
                    'cell_id': 'v4-C8192-r0',
                    'vcpu': 4,
                    'memory_mb': 8192,
                    'ratio_label': 'C',
                    'replicate': 0,
                }
            ]
        }

    def _patch_batch(self, monkeypatch, instance: str | None = 'c4.xlarge', status='SUCCEEDED'):
        monkeypatch.setattr(
            collect,
            'jobs_for_general_task',
            lambda gt_id: [{'jobId': 'j1', 'status': status, 'startedAt': 1_000_000, 'stoppedAt': 1_600_000}],
        )
        monkeypatch.setattr(collect, 'instance_type_by_job_id', lambda job_ids: {'j1': instance} if instance else {})

    def test_reads_metrics_from_toshi_java_log(self, monkeypatch):
        self._patch_batch(monkeypatch)
        toshi = _FakeToshiApi({'gt1': _subtasks_with_java_log('F1')}, {'F1': '\n'.join(SAMPLE_LOG)})
        rows = collect.collect_rows(self._manifest(), toshi_api=toshi)
        assert len(rows) == 1
        row = rows[0]
        assert row['iterations'] == 30388979
        assert row['perturbations'] == 1996244
        assert row['final_energy'] == 3631.1384
        assert row['instance_type'] == 'c4.xlarge'
        assert row['duration_sec'] == 600.0
        assert row['cost_usd'] is not None and row['iterations_per_usd'] is not None

    def test_access_denied_on_instance_types_degrades_to_no_cost(self, monkeypatch):
        from botocore.exceptions import ClientError

        monkeypatch.setattr(
            collect,
            'jobs_for_general_task',
            lambda gt_id: [{'jobId': 'j1', 'status': 'SUCCEEDED', 'startedAt': 1_000_000, 'stoppedAt': 1_600_000}],
        )

        def _deny(job_ids):
            raise ClientError(
                {'Error': {'Code': 'AccessDeniedException', 'Message': 'no'}}, 'DescribeContainerInstances'
            )

        monkeypatch.setattr(collect, 'instance_type_by_job_id', _deny)
        toshi = _FakeToshiApi({'gt1': _subtasks_with_java_log('F1')}, {'F1': '\n'.join(SAMPLE_LOG)})
        rows = collect.collect_rows(self._manifest(), toshi_api=toshi)
        row = rows[0]
        assert row['instance_type'] is None and row['cost_usd'] is None and row['iterations_per_usd'] is None
        assert row['iterations'] == 30388979  # metrics still collected without instance/cost

    def test_missing_java_log_yields_none_iterations(self, monkeypatch):
        self._patch_batch(monkeypatch, instance=None, status='FAILED')
        toshi = _FakeToshiApi({'gt1': {'children': {'edges': []}}})
        rows = collect.collect_rows(self._manifest(), toshi_api=toshi)
        assert rows[0]['iterations'] is None

    def test_toshi_error_does_not_abort_collection(self, monkeypatch):
        self._patch_batch(monkeypatch)
        toshi = _FakeToshiApi({}, error=RuntimeError('toshi down'))
        rows = collect.collect_rows(self._manifest(), toshi_api=toshi)
        assert len(rows) == 1
        assert rows[0]['iterations'] is None  # error swallowed per-cell, row still produced
        assert rows[0]['duration_sec'] == 600.0


class TestDurationSeconds:
    def test_completed_job_is_stopped_minus_started(self):
        assert collect.duration_seconds({'startedAt': 1_000_000, 'stoppedAt': 1_600_000}) == 600.0

    def test_missing_timestamp_is_none(self):
        assert collect.duration_seconds({'startedAt': 1_000_000}) is None
        assert collect.duration_seconds({}) is None


class TestJobCostUsd:
    def test_fair_share_cost_is_per_vcpu_prorated(self):
        # r4.2xlarge: 8 vCPU, $0.532/hr -> $0.0665 per vCPU-hr. A 4-vCPU job for 1 hour = 4 * 0.0665.
        cost = collect.job_cost_usd('r4.2xlarge', job_vcpu=4, seconds=3600.0)
        assert cost == round((0.532 / 8) * 4 * 1.0, 10)

    def test_scales_with_wall_time(self):
        full = collect.job_cost_usd('c4.2xlarge', 8, 3600.0)
        half = collect.job_cost_usd('c4.2xlarge', 8, 1800.0)
        assert full is not None and half is not None
        assert round(half, 10) == round(full / 2, 10)

    def test_unknown_instance_type_is_none(self):
        assert collect.job_cost_usd('t3.nano', 2, 3600.0) is None

    def test_missing_inputs_are_none(self):
        assert collect.job_cost_usd(None, 4, 3600.0) is None
        assert collect.job_cost_usd('c4.xlarge', 4, None) is None
