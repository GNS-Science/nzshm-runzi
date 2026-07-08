#!/usr/bin/env python
"""Collect and analyse the EC2 job-sizing benchmark for the coulomb rupture-set builder (#323).

The coulomb builder runs *to completion*, so the metric is **wall-clock time** (lower = better) and the
efficiency figure is **cost per completed build**. Both come straight from the AWS Batch job summary +
the instance type Batch placed the job on — there is **no Toshi log to parse** (that's inversion-only).

Given the manifest written by ``submit_coulomb_matrix.py``, this builds one row per cell with: the EC2
instance type, wall duration, and the fair-share cost. Emits a CSV and prints a per-cell summary ranked
by mean cost (cheapest first) with mean duration alongside, so both knees — cost-vs-vCPU and
time-vs-vCPU — are visible.

Cost is analytical, not raw billing: a benchmark under-packs instances, so we charge each job only for
the vCPUs it requested (see ``_cost.py``).

Usage::

    python scripts/ec2_sizing/collect_coulomb_results.py \
        --manifest scripts/ec2_sizing/coulomb_manifest.json --csv scripts/ec2_sizing/coulomb_results.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from botocore.exceptions import ClientError

from runzi.arguments import DEFAULT_JOB_QUEUE, EC2_JOB_QUEUE
from runzi.aws.batch_query import instance_type_by_job_id, jobs_for_general_task

# These scripts are loaded by file path (not as a package), so bootstrap the sibling module onto sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _cost import INSTANCE_SPECS, duration_seconds, job_cost_usd  # noqa: E402

# Exact-fit instance size for a given vCPU (job vCPU = instance vCPU on a pinned, one-job-per-size run).
VCPU_TO_SIZE = {2: 'large', 4: 'xlarge', 8: '2xlarge', 16: '4xlarge', 32: '8xlarge', 48: '12xlarge', 64: '16xlarge'}


def expected_instance_type(family: str | None, vcpu: int | None) -> str | None:
    """The exact-fit instance type for a pinned family + vCPU (e.g. c6a + 8 -> c6a.2xlarge), or ``None``.

    On a family-pinned run the instance is deterministic from family + vCPU, so we can price a run whose
    compute environment has already scaled to zero (ECS can no longer resolve the instance) without any
    read-back. And because $/hr scales linearly with size, the fair-share **per-vCPU** cost is identical
    whatever size Batch actually packed the job onto — so this stays correct even if Batch co-located jobs.
    """
    if not family or vcpu not in VCPU_TO_SIZE:
        return None
    candidate = f'{family}.{VCPU_TO_SIZE[vcpu]}'
    return candidate if candidate in INSTANCE_SPECS else None


def collect_rows(
    manifest: dict[str, Any],
    queues: tuple[str, ...] = (DEFAULT_JOB_QUEUE, EC2_JOB_QUEUE),
    instance_type_override: str | None = None,
) -> list[dict[str, Any]]:
    """Build one result row per manifest cell, joining Batch/EC2 wall duration with fair-share cost.

    ``queues`` is the set of Batch job queues to search for each cell's job — must include any pinned
    per-family benchmark queue, since those aren't in the standard set.

    ``instance_type_override`` forces the instance type for every row (a pinned run whose compute
    environment has since scaled to zero, so ECS can no longer resolve the instance), skipping the
    ECS/EC2 lookup.
    """
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
            # Without them we still report status/duration; only cost goes blank.
            print(f'warning: cannot resolve EC2 instance types, cost columns will be blank: {exc}', file=sys.stderr)

    results: list[dict[str, Any]] = []
    for gt_id, cell in rows_by_gt_id.items():
        jobs = jobs_by_gt_id[gt_id]
        summary = jobs[0] if jobs else {}  # oldest job; a coulomb submit produces exactly one
        job_id = summary.get('jobId')
        # Prefer the resolved type; fall back to the family-derived exact-fit type for pinned cells (rows
        # routed to a per-family queue), so cost survives the CE scaling to zero / no ECS read-back perms.
        derived = expected_instance_type(cell.get('family'), cell['vcpu']) if cell.get('job_queue') else None
        instance_type = instance_type_override or (instance_types.get(job_id) if job_id else None) or derived
        seconds = duration_seconds(summary)
        cost = job_cost_usd(instance_type, cell['vcpu'], seconds)
        results.append(
            {
                'cell_id': cell['cell_id'],
                'family': cell['family'],
                'vcpu': cell['vcpu'],
                'threads': cell.get('threads', cell['vcpu']),
                'memory_mb': cell['memory_mb'],
                'replicate': cell['replicate'],
                'general_task_id': gt_id,
                'job_id': job_id,
                'status': summary.get('status'),
                'instance_type': instance_type,
                'duration_sec': None if seconds is None else round(seconds, 1),
                'cost_usd': None if cost is None else round(cost, 5),
            }
        )
    return results


FIELDNAMES = [
    'cell_id',
    'family',
    'vcpu',
    'threads',
    'memory_mb',
    'replicate',
    'general_task_id',
    'job_id',
    'status',
    'instance_type',
    'duration_sec',
    'cost_usd',
]


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _mean(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def _fmt(value: object, unit: str = '') -> str:
    """Format a summary number: integer resolution, underscore thousands separators, or 'None'."""
    if not isinstance(value, (int, float)):
        return 'None'
    return f'{round(value):_}{unit}'


def _fmt_cost(value: object) -> str:
    return 'None' if not isinstance(value, (int, float)) else f'${value:.4f}'


def print_summary(rows: list[dict[str, Any]]) -> None:
    """Print a per-cell (family x vCPU) summary ranked by mean cost per build (cheapest first).

    Mean wall duration is shown alongside so the time-vs-vCPU knee is visible next to the cost-vs-vCPU
    knee. Cells with no priced cost (unresolved instance, or a failed/OOM build) sort last.
    """
    by_cell: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_cell[(row['family'], row['vcpu'])].append(row)

    summary = []
    for (family, vcpu), cell_rows in by_cell.items():
        durations = [r['duration_sec'] for r in cell_rows if r['duration_sec'] is not None]
        costs = [r['cost_usd'] for r in cell_rows if r['cost_usd'] is not None]
        statuses = sorted({r['status'] for r in cell_rows if r['status']})
        instances = sorted({r['instance_type'] for r in cell_rows if r['instance_type']})
        summary.append(
            {
                'family': family,
                'vcpu': vcpu,
                'n': len(cell_rows),
                'instances': ','.join(instances) or '-',
                'status': ','.join(statuses) or '-',
                'mean_duration': _mean(durations),
                'mean_cost': _mean(costs),
            }
        )
    # Cheapest first; unpriced cells (mean_cost None) sort to the bottom.
    summary.sort(key=lambda s: (s['mean_cost'] is None, s['mean_cost'] or 0.0))

    header = f'{"family":>7} {"vCPU":>4} {"n":>3} {"instances":>16} {"status":>18} {"mean_secs":>10} {"mean_cost":>11}'
    print(header)
    print('-' * len(header))
    for s in summary:
        print(
            f'{s["family"]:>7} {s["vcpu"]:>4} {s["n"]:>3} {s["instances"]:>16} {s["status"]:>18} '
            f'{_fmt(s["mean_duration"], "s"):>10} {_fmt_cost(s["mean_cost"]):>11}'
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        '--manifest',
        type=Path,
        default=Path(__file__).with_name('coulomb_manifest.json'),
        help='Manifest from submit_coulomb_matrix.py.',
    )
    parser.add_argument(
        '--csv',
        type=Path,
        default=Path(__file__).with_name('coulomb_results.csv'),
        help='Where to write the per-job CSV.',
    )
    parser.add_argument(
        '--queues',
        nargs='+',
        default=None,
        help="Batch job queues to search (default: the manifest's per-cell queues plus the standard queues).",
    )
    parser.add_argument(
        '--instance-type',
        default=None,
        help='Force the instance type for every row (a pinned run whose compute environment has scaled to zero, '
        'when ECS can no longer resolve the instance).',
    )
    args = parser.parse_args(argv)

    manifest = json.loads(args.manifest.read_text())
    # Search the manifest's own per-cell queues (pinned benchmark queues aren't in the standard set) plus
    # the standard queues, unless --queues overrides. dict.fromkeys de-dupes while keeping order.
    if args.queues:
        queues = tuple(args.queues)
    else:
        manifest_queues = [row.get('job_queue') for row in manifest['rows']]
        queues = tuple(dict.fromkeys([q for q in (*manifest_queues, DEFAULT_JOB_QUEUE, EC2_JOB_QUEUE) if q]))
    rows = collect_rows(manifest, queues=queues, instance_type_override=args.instance_type)
    write_csv(rows, args.csv)
    print(f'wrote {len(rows)} rows to {args.csv}\n')

    unpriced = sorted(
        {r['instance_type'] for r in rows if r['instance_type'] and r['instance_type'] not in INSTANCE_SPECS}
    )
    if unpriced:
        print(f'warning: no price for {", ".join(unpriced)} — add to _cost.py for their cost.\n', file=sys.stderr)

    print_summary(rows)
    return 0


if __name__ == '__main__':
    sys.exit(main())
