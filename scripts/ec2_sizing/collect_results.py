#!/usr/bin/env python
"""Collect and analyse the EC2 job-sizing benchmark results (#323, Phase 1).

Given the manifest written by ``submit_matrix.py``, this builds one row per cell with: the actual EC2
instance type Batch placed the job on, wall duration, the anneal iterations completed, a computed
fair-share cost, and iterations-per-dollar. Emits a CSV and prints a summary ranking cells.

Two data sources are joined per cell (both keyed by the manifest's ``general_task_id``):
  - **AWS Batch/EC2** for cost inputs — the instance type and wall duration of the cell's job.
  - **Toshi** for the iteration count — the inversion uploads its ``java_app.<port>.log`` as a task
    file (the count is NOT in the CloudWatch log), so we fetch and parse that log.

Cost is analytical, not raw billing: a benchmark under-packs instances, so we charge each job only for
the vCPUs it requested — ``(instance $/hr / instance vCPU) x job vCPU x wall-hours`` — the cost it
would carry on a fully-packed production instance.

Usage::

    python scripts/ec2_sizing/collect_results.py --manifest scripts/ec2_sizing/manifest.json \
        --csv scripts/ec2_sizing/results.csv

If the iteration count is logged in a different shape than the default regex expects, pass
``--iteration-regex`` to match it (capture group 1 = the integer).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from botocore.exceptions import ClientError

from runzi.arguments import DEFAULT_JOB_QUEUE, EC2_JOB_QUEUE
from runzi.aws.batch_query import instance_type_by_job_id, jobs_for_general_task

# The EC2 price table + fair-share cost formula are task-agnostic and shared with the coulomb collector.
# These scripts are loaded by file path (not as a package), so bootstrap the sibling module onto sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _cost import INSTANCE_SPECS, duration_seconds, job_cost_usd  # noqa: E402

if TYPE_CHECKING:
    from runzi.automation.toshi_api import ToshiApi

# The annealer prints summary lines `Total Iterations: <n>` and `Total Perturbations: <n>` in
# java_app.<port>.log. Anchor on each exact phrase (so `Total Perturbations`, the energy block's
# `Total:`, and other "iter"-ish text aren't confused); the capture must start with a digit (thousands
# separators tolerated) so a stray comma can't match as an empty count. --iteration-regex overrides the
# iteration pattern if the log format changes (group 1 = the integer).
DEFAULT_ITERATION_REGEX = r'(?i)total\s+iterations[^0-9]*([0-9][0-9,]*)'
PERTURBATIONS_REGEX = r'(?i)total\s+perturbations[^0-9]*([0-9][0-9,]*)'
# The final solution quality: the `Total:` value on the line following a `Best energy:` header.
_BEST_ENERGY_HEADER = re.compile(r'(?i)best\s+energy')
_ENERGY_TOTAL = re.compile(r'(?i)\btotal:\s*([0-9]+(?:\.[0-9]+)?)')


def parse_max_int(lines: list[str], pattern: str) -> int | None:
    """Return the largest integer captured (group 1) by ``pattern`` across the log lines, or ``None``.

    Counts only grow, so the max match is the final value regardless of how often progress prints. A
    capture with no digits after stripping commas is skipped, so a stray-comma capture (or a loose
    custom pattern) can't raise ``ValueError``.
    """
    regex = re.compile(pattern)
    best: int | None = None
    for line in lines:
        for match in regex.finditer(line):
            digits = match.group(1).replace(',', '')
            if not digits.isdigit():
                continue
            value = int(digits)
            best = value if best is None else max(best, value)
    return best


def parse_final_energy(lines: list[str]) -> float | None:
    """Return the ``Total:`` energy from the last ``Best energy:`` block, or ``None`` if absent.

    The annealer prints a ``Best energy:`` header followed by a ``Total:  <float>`` line (plus per-
    constraint terms). Energy falls over the run, so the last block is the final solution quality.
    """
    energy: float | None = None
    for index, line in enumerate(lines):
        if _BEST_ENERGY_HEADER.search(line):
            for probe in lines[index : index + 3]:  # header line + the Total: line just after it
                match = _ENERGY_TOTAL.search(probe)
                if match:
                    energy = float(match.group(1))
                    break
    return energy


def build_toshi_api() -> ToshiApi:
    """Construct a ToshiApi client the same way the task modules do (auth from local_config / .env)."""
    from runzi.automation.local_config import API_URL, S3_URL, get_auth_kwargs
    from runzi.automation.toshi_api import ToshiApi

    return ToshiApi(API_URL, S3_URL, None, with_schema_validation=False, **get_auth_kwargs())


def java_log_file_id(subtasks_response: dict[str, Any]) -> str | None:
    """Return the id of the ``java_app.<port>.log`` file among a general task's subtask files, or None.

    ``subtasks_response`` is the shape returned by ``ToshiApi.get_general_task_subtask_files``: the
    general task node with ``children.edges[].node.child.files.edges[].node.file``. A plain crustal
    submit has one subtask, which uploads exactly one such log.
    """
    for edge in subtasks_response.get('children', {}).get('edges', []):
        child = edge.get('node', {}).get('child', {})
        for file_edge in child.get('files', {}).get('edges', []):
            file = file_edge.get('node', {}).get('file', {})
            name = file.get('file_name', '')
            if name.startswith('java_app') and name.endswith('.log'):
                return file.get('id')
    return None


_EMPTY_METRICS: dict[str, Any] = {'iterations': None, 'perturbations': None, 'final_energy': None}


def metrics_for_general_task(
    toshi_api: ToshiApi, gt_id: str, iteration_regex: str, download_dir: Path
) -> dict[str, Any]:
    """Fetch the general task's java_app log from Toshi and parse iterations, perturbations, and energy.

    Returns ``{'iterations', 'perturbations', 'final_energy'}`` (any value ``None`` if not found); the
    log is downloaded once and all three parsed from it.
    """
    subtasks = toshi_api.get_general_task_subtask_files(gt_id)
    file_id = java_log_file_id(subtasks)
    if file_id is None:
        return dict(_EMPTY_METRICS)
    path = toshi_api.file.download_file(file_id, str(download_dir))
    lines = Path(path).read_text(errors='replace').splitlines()
    return {
        'iterations': parse_max_int(lines, iteration_regex),
        'perturbations': parse_max_int(lines, PERTURBATIONS_REGEX),
        'final_energy': parse_final_energy(lines),
    }


def collect_rows(
    manifest: dict[str, Any],
    iteration_regex: str = DEFAULT_ITERATION_REGEX,
    toshi_api: ToshiApi | None = None,
    queues: tuple[str, ...] = (DEFAULT_JOB_QUEUE, EC2_JOB_QUEUE),
    instance_type_override: str | None = None,
) -> list[dict[str, Any]]:
    """Build one result row per manifest cell, joining Batch/EC2 cost data with Toshi iteration counts.

    ``queues`` is the set of Batch job queues to search for each cell's job — must include any custom
    Phase-2 benchmark queue, since those aren't in the standard set.

    ``instance_type_override`` forces the instance type for every row (a pinned Phase-2 run: the type is
    known from the pinned queue), skipping the ECS/EC2 lookup — which only works while the container
    instances are still registered, and returns nothing once the compute environment scales to zero.
    """
    if toshi_api is None:
        toshi_api = build_toshi_api()
    rows_by_gt_id = {row['general_task_id']: row for row in manifest['rows']}

    # Each cell is its own submit -> one general task -> one Batch job. Fetch each cell's job(s) once,
    # then price all instance types in a single batched lookup (unless the type is pinned/overridden).
    jobs_by_gt_id = {gt_id: jobs_for_general_task(gt_id, queues=queues) for gt_id in rows_by_gt_id}
    all_job_ids = [job['jobId'] for jobs in jobs_by_gt_id.values() for job in jobs]
    instance_types: dict[str, str] = {}
    if instance_type_override is None:
        try:
            instance_types = instance_type_by_job_id(all_job_ids)
        except ClientError as exc:
            # Resolving instance types needs ecs:DescribeContainerInstances + ec2:DescribeInstances.
            # Without them we still report iterations/perturbations/energy; only cost goes blank.
            print(f'warning: cannot resolve EC2 instance types, cost columns will be blank: {exc}', file=sys.stderr)

    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix='ec2_sizing_logs_') as tmp:
        download_dir = Path(tmp)
        for gt_id, cell in rows_by_gt_id.items():
            jobs = jobs_by_gt_id[gt_id]
            summary = jobs[0] if jobs else {}  # oldest job; a crustal submit produces exactly one
            job_id = summary.get('jobId')
            instance_type = instance_type_override or (instance_types.get(job_id) if job_id else None)
            seconds = duration_seconds(summary)
            try:
                metrics = metrics_for_general_task(toshi_api, gt_id, iteration_regex, download_dir)
            except Exception as exc:  # one cell's missing/undownloadable log must not abort the rest
                print(f'warning: could not read metrics for {cell["cell_id"]} ({gt_id}): {exc}', file=sys.stderr)
                metrics = dict(_EMPTY_METRICS)
            iterations = metrics['iterations']
            cost = job_cost_usd(instance_type, cell['vcpu'], seconds)
            results.append(
                {
                    'cell_id': cell['cell_id'],
                    'vcpu': cell['vcpu'],
                    'memory_mb': cell['memory_mb'],
                    'ratio_label': cell['ratio_label'],
                    'replicate': cell['replicate'],
                    'general_task_id': gt_id,
                    'job_id': job_id,
                    'status': summary.get('status'),
                    'instance_type': instance_type,
                    'duration_sec': None if seconds is None else round(seconds, 1),
                    'iterations': iterations,
                    'perturbations': metrics['perturbations'],
                    'final_energy': metrics['final_energy'],
                    'cost_usd': None if cost is None else round(cost, 5),
                    'iterations_per_usd': (round(iterations / cost, 1) if iterations is not None and cost else None),
                }
            )
    return results


FIELDNAMES = [
    'cell_id',
    'vcpu',
    'memory_mb',
    'ratio_label',
    'replicate',
    'general_task_id',
    'job_id',
    'status',
    'instance_type',
    'duration_sec',
    'iterations',
    'perturbations',
    'final_energy',
    'cost_usd',
    'iterations_per_usd',
]


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _mean(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def _fmt_int(value: object) -> str:
    """Format for the summary table: integer resolution, underscore thousands separators, or 'None'."""
    if not isinstance(value, (int, float)):
        return 'None'
    return f'{round(value):_}'


def print_summary(rows: list[dict[str, Any]]) -> None:
    """Print a per-cell (vCPU x ratio) summary ranked by mean iterations-per-dollar."""
    by_cell: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_cell[(row['vcpu'], row['ratio_label'])].append(row)

    summary = []
    for (vcpu, ratio), cell_rows in by_cell.items():
        iters = [r['iterations'] for r in cell_rows if r['iterations'] is not None]
        perts = [r['perturbations'] for r in cell_rows if r['perturbations'] is not None]
        energies = [r['final_energy'] for r in cell_rows if r['final_energy'] is not None]
        ipd = [r['iterations_per_usd'] for r in cell_rows if r['iterations_per_usd'] is not None]
        instances = sorted({r['instance_type'] for r in cell_rows if r['instance_type']})
        summary.append(
            {
                'vcpu': vcpu,
                'ratio': ratio,
                'n': len(cell_rows),
                'instances': ','.join(instances) or '-',
                'mean_iterations': _mean(iters),
                'mean_perturbations': _mean(perts),
                'mean_energy': _mean(energies),
                'mean_iter_per_usd': _mean(ipd),
            }
        )
    summary.sort(key=lambda s: (s['mean_iter_per_usd'] is not None, s['mean_iter_per_usd'] or 0), reverse=True)

    header = (
        f'{"vCPU":>4} {"ratio":>5} {"n":>3} {"instances":>22} '
        f'{"mean_iters":>15} {"mean_perts":>13} {"mean_energy":>12} {"iters/$":>16}'
    )
    print(header)
    print('-' * len(header))
    for s in summary:
        print(
            f'{s["vcpu"]:>4} {s["ratio"]:>5} {s["n"]:>3} {s["instances"]:>22} '
            f'{_fmt_int(s["mean_iterations"]):>15} {_fmt_int(s["mean_perturbations"]):>13} '
            f'{_fmt_int(s["mean_energy"]):>12} {_fmt_int(s["mean_iter_per_usd"]):>16}'
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        '--manifest',
        type=Path,
        default=Path(__file__).with_name('manifest.json'),
        help='Manifest from submit_matrix.py.',
    )
    parser.add_argument(
        '--csv', type=Path, default=Path(__file__).with_name('results.csv'), help='Where to write the per-job CSV.'
    )
    parser.add_argument(
        '--iteration-regex',
        default=DEFAULT_ITERATION_REGEX,
        help='Regex whose group 1 captures the iteration integer in a log line.',
    )
    parser.add_argument(
        '--queues',
        nargs='+',
        default=None,
        help='Batch job queues to search (default: the manifest\'s job_queue plus the standard queues).',
    )
    parser.add_argument(
        '--instance-type',
        default=None,
        help='Force the instance type for every row (a pinned Phase-2 run). Use this to price runs whose '
        'compute environment has since scaled to zero, when ECS can no longer resolve the instance.',
    )
    args = parser.parse_args(argv)

    manifest = json.loads(args.manifest.read_text())
    # Search the manifest's own queue (Phase-2 benchmark queues aren't in the standard set) plus the
    # standard queues, unless --queues overrides. dict.fromkeys de-dupes while keeping order.
    if args.queues:
        queues = tuple(args.queues)
    else:
        manifest_queue = manifest.get('job_queue')
        queues = tuple(dict.fromkeys([q for q in (manifest_queue, DEFAULT_JOB_QUEUE, EC2_JOB_QUEUE) if q]))
    rows = collect_rows(manifest, args.iteration_regex, queues=queues, instance_type_override=args.instance_type)
    write_csv(rows, args.csv)
    print(f'wrote {len(rows)} rows to {args.csv}\n')

    unpriced = sorted(
        {r['instance_type'] for r in rows if r['instance_type'] and r['instance_type'] not in INSTANCE_SPECS}
    )
    if unpriced:
        print(f'warning: no price for {", ".join(unpriced)} — add to INSTANCE_SPECS for their cost.\n', file=sys.stderr)

    print_summary(rows)
    return 0


if __name__ == '__main__':
    sys.exit(main())
