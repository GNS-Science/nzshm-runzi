#!/usr/bin/env python
"""Submit the EC2 job-sizing benchmark matrix for crustal inversions (#323, Phase 1).

Each matrix cell is its own ``runzi inversion crustal`` submit with distinct
``submission_arg_overrides`` (``ecs_vcpu`` / ``ecs_memory``) targeting the EC2 compute environment.
This is required because ``swept_args`` fan out *task args* under a single ``SubmissionArgs`` and so
cannot sweep the submission-side sizing fields.

The anneal thread count (``selector_threads`` x ``averaging_threads`` = 16) and the rupture set are
held constant across cells — they live in the template config, not here — so cells vary only vCPU and
memory. The memory:vCPU ratio nudges which "optimal" instance family Batch picks (~2:1 C, ~4:1 M,
~8:1 R); the actual instance is read back at analysis time (see ``collect_results.py``).

Usage::

    # Dry run: render + print the configs, no AWS calls.
    python scripts/ec2_sizing/submit_matrix.py --dry-run

    # Real submit (needs AWS creds + toshi API): writes a manifest of general_task_ids.
    python scripts/ec2_sizing/submit_matrix.py --manifest scripts/ec2_sizing/manifest.json

Feed the resulting manifest to ``collect_results.py`` once the jobs finish.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# vCPU counts to test. 16 is the natural top: the inversion runs 16 anneal threads (fixed), so more
# cores buys nothing; 4 and 8 deliberately oversubscribe to price the cost/throughput tradeoff.
VCPUS = (4, 8, 16)

# memory:vCPU ratio -> MB per vCPU. Nudges the "optimal" family Batch picks (C/M/R). Family targeting
# is approximate — Batch picks the smallest instance that fits, and the analysis uses the instance it
# actually landed on, so these need not be exact.
RATIOS_MB_PER_VCPU = {'C': 2048, 'M': 4096, 'R': 8192}

DEFAULT_REPLICATES = 3
TEMPLATE = Path(__file__).with_name('crustal_inversion.template.json')


@dataclass(frozen=True)
class Cell:
    """One matrix cell: a (vCPU, memory) point plus its replicate index."""

    vcpu: int
    memory_mb: int
    ratio_label: str
    replicate: int

    @property
    def cell_id(self) -> str:
        return f'v{self.vcpu}-{self.ratio_label}{self.memory_mb}-r{self.replicate}'


def build_cells(replicates: int, ratios: list[str] | None = None, vcpus: list[int] | None = None) -> list[Cell]:
    """Return the vcpus x ratios x replicates grid, in a stable order (all vCPUs/ratios unless given)."""
    ratios = ratios if ratios is not None else list(RATIOS_MB_PER_VCPU)
    vcpus = vcpus if vcpus is not None else list(VCPUS)
    cells: list[Cell] = []
    for vcpu in vcpus:
        for label in ratios:
            mb_per_vcpu = RATIOS_MB_PER_VCPU[label]
            for replicate in range(replicates):
                cells.append(Cell(vcpu=vcpu, memory_mb=vcpu * mb_per_vcpu, ratio_label=label, replicate=replicate))
    return cells


def render_config(
    template: dict[str, Any],
    cell: Cell,
    max_inversion_time: float | None,
    max_job_time_min: int,
    job_definition: str,
    memory_mb: int | None = None,
    job_queue: str | None = None,
) -> dict[str, Any]:
    """Return a per-cell crustal-inversion config: the template plus this cell's EC2 sizing overrides.

    ``ecs_job_definition`` selects the target and the queue/compute-environment derive from it via
    ``JOB_DEFINITION_TARGETS`` (ADR-0008); JVM heap follows ``ecs_memory`` automatically in ``aws.py``.
    ``memory_mb`` overrides the cell's ratio-derived memory (Phase 2: a constant that fits every pinned
    instance). ``job_queue`` overrides the derived queue to route to a specific benchmark CE's queue.
    """
    config = copy.deepcopy(template)
    if max_inversion_time is not None:
        config['max_inversion_time'] = max_inversion_time
    overrides: dict[str, Any] = {
        'ecs_vcpu': cell.vcpu,
        'ecs_memory': memory_mb if memory_mb is not None else cell.memory_mb,
        'ecs_job_definition': job_definition,
        'ecs_max_job_time_min': max_job_time_min,
    }
    if job_queue is not None:
        overrides['ecs_job_queue'] = job_queue
    config['submission_arg_overrides'] = overrides
    return config


def submit_cell(config: dict[str, Any]) -> str:
    """Submit one rendered config to AWS Batch and return its toshi general_task_id.

    Calls the runner directly (as ``inversion_cli.crustal`` does) rather than shelling out, so the
    general_task_id comes back as a clean return value. Sets ``local_config`` to AWS/API mode first,
    exactly as the CLI's main callback does.
    """
    import runzi.automation.local_config as local_config
    from runzi.arguments import ArgSweeper
    from runzi.automation.local_config import ClusterModeEnum
    from runzi.tasks.inversion import CrustalInversionArgs, CrustalInversionJobRunner

    local_config.CLUSTER_MODE = ClusterModeEnum.AWS
    local_config.USE_API = True

    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as handle:
        json.dump(config, handle)
        config_path = Path(handle.name)
    try:
        job_input = ArgSweeper.from_config_file(config_path, CrustalInversionArgs)
        gt_id = CrustalInversionJobRunner(job_input).run_jobs()
    finally:
        config_path.unlink(missing_ok=True)
    if gt_id is None:  # USE_API is forced True above, so a general_task_id is always created.
        raise RuntimeError('run_jobs() returned no general_task_id; is the toshi API configured?')
    return gt_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--template', type=Path, default=TEMPLATE, help='Crustal inversion template config JSON.')
    parser.add_argument(
        '--max-inversion-time', type=float, default=None, help='Override max_inversion_time (minutes) in the template.'
    )
    parser.add_argument(
        '--max-job-time-min',
        type=int,
        default=30,
        help='Batch job time limit (minutes); must exceed max_inversion_time plus IO/JVM overhead.',
    )
    parser.add_argument('--replicates', type=int, default=DEFAULT_REPLICATES, help='Repeats per cell.')
    parser.add_argument(
        '--ratios',
        nargs='+',
        choices=list(RATIOS_MB_PER_VCPU),
        default=None,
        help='Which memory:vCPU ratios to include (default all). E.g. --ratios C M drops the 8:1 R cells.',
    )
    parser.add_argument(
        '--vcpus',
        nargs='+',
        type=int,
        choices=list(VCPUS),
        default=None,
        help='Which vCPU counts to include (default all). E.g. --vcpus 8 for a Phase-2 single-size run.',
    )
    parser.add_argument(
        '--memory-mb',
        type=int,
        default=None,
        help='Override ecs_memory (MB) for every cell, ignoring the ratio grid (Phase 2: a constant that '
        'fits each pinned instance, e.g. 14000 to fit c6i.2xlarge).',
    )
    parser.add_argument(
        '--job-queue',
        default=None,
        help='Override the Batch job queue (Phase 2: route to a specific pinned-instance benchmark queue). '
        'The EC2 job definition is unchanged, so the compute-environment type stays EC2.',
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Submit only the first N cells of the grid (e.g. --limit 1 for a single-cell pilot).',
    )
    parser.add_argument(
        '--manifest',
        type=Path,
        default=Path(__file__).with_name('manifest.json'),
        help='Where to write the {cell -> general_task_id} manifest.',
    )
    parser.add_argument(
        '--prod',
        action='store_true',
        help='Target the :prod EC2 job definition instead of the default :experimental one.',
    )
    parser.add_argument('--dry-run', action='store_true', help='Render and print configs without submitting.')
    args = parser.parse_args(argv)

    from runzi.arguments import EC2_EXPERIMENTAL_JOB_DEFINITION, EC2_JOB_DEFINITION

    # Default to the :experimental JD: a benchmark should exercise the latest-built image, and :prod may
    # lag main (an out-of-date worker manifests as a py4j `127.0.0.1:None` gateway error).
    job_definition = EC2_JOB_DEFINITION if args.prod else EC2_EXPERIMENTAL_JOB_DEFINITION

    template = json.loads(args.template.read_text())
    cells = build_cells(args.replicates, args.ratios, args.vcpus)
    full_grid = len(cells)
    if args.limit is not None:
        cells = cells[: args.limit]

    ratios = args.ratios if args.ratios is not None else list(RATIOS_MB_PER_VCPU)
    vcpus = args.vcpus if args.vcpus is not None else list(VCPUS)
    target = args.job_queue if args.job_queue is not None else job_definition
    print(
        f'submitting {len(cells)} of {full_grid} cells to {target} '
        f'({len(vcpus)} vCPU {vcpus} x {len(ratios)} ratios {ratios} x {args.replicates} replicates'
        f'{f", memory {args.memory_mb} MB" if args.memory_mb is not None else ""})'
    )

    manifest_rows: list[dict[str, Any]] = []
    for cell in cells:
        config = render_config(
            template,
            cell,
            args.max_inversion_time,
            args.max_job_time_min,
            job_definition,
            memory_mb=args.memory_mb,
            job_queue=args.job_queue,
        )
        if args.dry_run:
            print(f'--- {cell.cell_id} (vcpu={cell.vcpu} memory_mb={cell.memory_mb}) ---')
            print(json.dumps(config['submission_arg_overrides']))
            continue
        gt_id = submit_cell(config)
        print(f'{cell.cell_id}: general_task_id={gt_id}')
        manifest_rows.append({**asdict(cell), 'cell_id': cell.cell_id, 'general_task_id': gt_id})

    if args.dry_run:
        return 0

    manifest = {
        'submitted_at': dt.datetime.now(dt.UTC).isoformat(),
        'max_inversion_time': args.max_inversion_time
        if args.max_inversion_time is not None
        else template.get('max_inversion_time'),
        'rows': manifest_rows,
    }
    args.manifest.write_text(json.dumps(manifest, indent=2))
    print(f'wrote manifest: {args.manifest} ({len(manifest_rows)} submits)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
