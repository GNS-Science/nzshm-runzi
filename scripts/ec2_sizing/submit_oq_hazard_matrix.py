#!/usr/bin/env python
"""Submit the EC2 job-sizing benchmark matrix for the OpenQuake **hazard** task (#344).

Like the coulomb rupture-set builder (#343), OQ hazard runs *to completion*, so the metric is
**wall-clock time** and the knobs that matter are **cores** and **instance family**. Like coulomb, the
core budget must be **pinned** per cell: on AWS Batch EC2 the container sees the *host's* cores (CPU
shares, not cpuset), so an uncapped OpenQuake sizes its processpool to the whole instance and OOM-kills
a memory-capped container (#344). Each cell therefore ships ``num_cores = ecs_vcpu`` (fed through to
``openquake.cfg [distribution] num_cores`` by ``execute_openquake``), so the vCPU axis is real. Memory
follows the family's per-vCPU ratio, so a compute-optimized (c-family, ~2 GB/vCPU) cell that OOMs
*reveals* that hazard needs more RAM than c-family provides. Each matrix cell is its own
``runzi hazard oq_hazard`` submit with distinct ``submission_arg_overrides``:

  - ``ecs_vcpu`` = the cell's core count,
  - ``num_cores`` = ``ecs_vcpu`` (caps OpenQuake's processpool so each cell uses exactly the cores it
    pays for and doesn't OOM on EC2 — see #344),
  - ``ecs_memory`` = sized to ~fill the family's per-vCPU RAM.

``swept_args`` can't sweep submission-side sizing fields, hence one submit per cell.

The template (``oq_hazard.template.json``) uses the full 2022 GMCM logic tree (from ``NSHM_v1.0.4``) and a
**single SRM branch** (``srm_single_branch_TEST.json``, co-located so it resolves) so each submit is
exactly **one** Batch job — the collector assumes one submit -> one job.

Instance families are pinned by routing each cell to a per-family Batch queue (stood up by
``terraform/ec2-sizing-benchmark/``). Pass ``--queue-prefix`` (the terraform ``name_prefix``, default
``ec2sizing``); each cell then targets ``{prefix}-{family}-Q``. Without ``--queue-prefix`` all cells go to
the job definition's derived ``runzi-ec2`` queue (an unpinned smoke test, where Batch "optimal" picks
the instance).

Usage::

    # Dry run: render + print the per-cell overrides, no AWS calls.
    python scripts/ec2_sizing/submit_oq_hazard_matrix.py --dry-run

    # Pilot: ONE cell to confirm the image + wall-clock path before spending the full matrix.
    python scripts/ec2_sizing/submit_oq_hazard_matrix.py --limit 1 --manifest scratch/pilot.json

    # Full matrix, families pinned via the terraform benchmark queues.
    python scripts/ec2_sizing/submit_oq_hazard_matrix.py --queue-prefix ec2sizing \
        --manifest scripts/ec2_sizing/oq_hazard_manifest.json

Feed the resulting manifest to ``collect_oq_hazard_results.py`` once the jobs finish.
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

# Allowed --vcpus values (argparse choices). Spans 16x to expose the parallel-scaling knee.
VCPUS = (4, 8, 16, 32, 64)
# Default grid. Excludes 64: the 2026-07 run put the knee at 32 (32->64 is a ~5x-worse-value cliff, like
# coulomb's), so 64 is opt-in via `--vcpus 64` — worth adding only if a new workload is still scaling at 32.
DEFAULT_VCPUS = (4, 8, 16, 32)

# family -> MB per vCPU. Sized to ~fill each family's per-vCPU RAM (leaving agent headroom under the
# instance ceiling: c/m/r ~= 2/4/8 GB per vCPU), so a c-family OOM is the signal that hazard needs more
# than 2 GB/vCPU. The family also selects the pinned Batch queue ({prefix}-{family}-Q).
FAMILY_MB_PER_VCPU = {'c6a': 1800, 'm6a': 3800, 'r6a': 7600, 'c6i': 1800, 'm6i': 3800, 'r6i': 7600}

DEFAULT_FAMILIES = ('c6a', 'm6a')  # compute-optimized vs general purpose, both AMD (cheapest x86)
DEFAULT_REPLICATES = 2
DEFAULT_QUEUE_PREFIX = 'ec2sizing'  # matches terraform/ec2-sizing-benchmark var.name_prefix
TEMPLATE = Path(__file__).with_name('oq_hazard.template.json')


@dataclass(frozen=True)
class Cell:
    """One matrix cell: an (instance family, vCPU) point plus its replicate index.

    There is deliberately no separate thread field: the OpenQuake core cap (``num_cores``) is always
    pinned to ``vcpu`` in ``render_config``, so it isn't an independent axis (unlike coulomb's builder,
    where threads could be swept apart from vCPU).
    """

    family: str
    vcpu: int
    memory_mb: int
    replicate: int

    @property
    def cell_id(self) -> str:
        return f'{self.family}-v{self.vcpu}-r{self.replicate}'


def build_cells(replicates: int, families: list[str] | None = None, vcpus: list[int] | None = None) -> list[Cell]:
    """Return the families x vcpus x replicates grid, in a stable order (all families/vCPUs unless given)."""
    families = families if families is not None else list(DEFAULT_FAMILIES)
    vcpus = vcpus if vcpus is not None else list(DEFAULT_VCPUS)
    cells: list[Cell] = []
    for family in families:
        mb_per_vcpu = FAMILY_MB_PER_VCPU[family]
        for vcpu in vcpus:
            for replicate in range(replicates):
                cells.append(Cell(family=family, vcpu=vcpu, memory_mb=vcpu * mb_per_vcpu, replicate=replicate))
    return cells


def queue_for(cell: Cell, queue_prefix: str | None) -> str | None:
    """The pinned Batch queue for a cell's family, or ``None`` (use the JD-derived runzi-ec2 queue)."""
    return None if queue_prefix is None else f'{queue_prefix}-{cell.family}-Q'


def render_config(
    template: dict[str, Any],
    cell: Cell,
    max_job_time_min: int,
    job_definition: str,
    queue_prefix: str | None = None,
) -> dict[str, Any]:
    """Return a per-cell OQ hazard config: the template plus this cell's EC2 sizing overrides.

    ``ecs_job_definition`` selects the target and the queue/compute-environment derive from it via
    ``JOB_DEFINITION_TARGETS`` (ADR-0008), unless a ``queue_prefix`` routes the cell to a pinned
    per-family benchmark queue (the JD is unchanged, so the compute-environment type stays EC2).
    ``num_cores`` is pinned to ``ecs_vcpu`` to cap OpenQuake's processpool (else it grabs the host's
    cores and OOMs on EC2 — #344).
    """
    config = copy.deepcopy(template)
    overrides: dict[str, Any] = {
        'ecs_vcpu': cell.vcpu,
        # Cap OpenQuake's processpool to the cell's vCPU. On AWS Batch EC2 the container sees the host's
        # cores (CPU shares, not cpuset), so without this OQ sizes its pool to the whole instance and OOMs
        # a memory-capped container (#344). Shipped via the num_cores TaskRuntimeArg; the OQ task feeds
        # it to execute_openquake, which writes it to openquake.cfg [distribution] num_cores.
        'num_cores': cell.vcpu,
        'ecs_memory': cell.memory_mb,
        'ecs_job_definition': job_definition,
        'ecs_max_job_time_min': max_job_time_min,
    }
    queue = queue_for(cell, queue_prefix)
    if queue is not None:
        overrides['ecs_job_queue'] = queue
    config['submission_arg_overrides'] = overrides
    return config


def submit_cell(config: dict[str, Any], config_dir: Path) -> str:
    """Submit one rendered config to AWS Batch and return its toshi general_task_id.

    Calls the runner directly (as ``hazard_cli.oq_hazard`` does) rather than shelling out, so the
    general_task_id comes back as a clean return value. Sets ``local_config`` to AWS/API mode first,
    exactly as the CLI's main callback does. ``USE_API`` is required: the general_task_id it mints is the
    only link back to the cell's Batch job.

    The temp config is written into ``config_dir`` (the template's directory) so the template's relative
    ``srm_logic_tree`` path resolves against the co-located file — ``ArgSweeper.from_config_file`` uses
    the config file's parent as the base path.
    """
    import runzi.automation.local_config as local_config
    from runzi.arguments import ArgSweeper
    from runzi.automation.local_config import ClusterModeEnum
    from runzi.tasks.oq_hazard import OQHazardArgs, OQHazardJobRunner

    local_config.CLUSTER_MODE = ClusterModeEnum.AWS
    local_config.USE_API = True

    with tempfile.NamedTemporaryFile('w', suffix='.json', dir=config_dir, delete=False) as handle:
        json.dump(config, handle)
        config_path = Path(handle.name)
    try:
        job_input = ArgSweeper.from_config_file(config_path, OQHazardArgs)
        gt_id = OQHazardJobRunner(job_input).run_jobs()
    finally:
        config_path.unlink(missing_ok=True)
    if gt_id is None:  # USE_API is forced True above, so a general_task_id is always created.
        raise RuntimeError('run_jobs() returned no general_task_id; is the toshi API configured?')
    return gt_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--template', type=Path, default=TEMPLATE, help='OQ hazard template config JSON.')
    parser.add_argument(
        '--max-job-time-min',
        type=int,
        default=240,
        help='Batch job time limit (minutes); must exceed the slowest (low-vCPU) hazard run plus IO overhead.',
    )
    parser.add_argument('--replicates', type=int, default=DEFAULT_REPLICATES, help='Repeats per cell.')
    parser.add_argument(
        '--families',
        nargs='+',
        choices=list(FAMILY_MB_PER_VCPU),
        default=None,
        help='Which instance families to include (default c6a m6a). Each maps to a pinned queue and a memory ratio.',
    )
    parser.add_argument(
        '--vcpus',
        nargs='+',
        type=int,
        choices=list(VCPUS),
        default=None,
        help=f'Which vCPU counts to include (default {list(DEFAULT_VCPUS)}; 64 is opt-in, past the knee).',
    )
    parser.add_argument(
        '--queue-prefix',
        default=None,
        help='Route each cell to the pinned per-family queue {prefix}-{family}-Q (the terraform name_prefix, '
        f'e.g. {DEFAULT_QUEUE_PREFIX!r}). Omit to use the JD-derived runzi-ec2 queue (unpinned smoke test).',
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
        default=Path(__file__).with_name('oq_hazard_manifest.json'),
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
    # lag main.
    job_definition = EC2_JOB_DEFINITION if args.prod else EC2_EXPERIMENTAL_JOB_DEFINITION

    template = json.loads(args.template.read_text())
    cells = build_cells(args.replicates, args.families, args.vcpus)
    full_grid = len(cells)
    if args.limit is not None:
        cells = cells[: args.limit]

    families = args.families if args.families is not None else list(DEFAULT_FAMILIES)
    vcpus = args.vcpus if args.vcpus is not None else list(DEFAULT_VCPUS)
    target = f'{args.queue_prefix}-*-Q' if args.queue_prefix is not None else job_definition
    print(
        f'submitting {len(cells)} of {full_grid} cells to {target} '
        f'({len(families)} families {families} x {len(vcpus)} vCPU {vcpus} x {args.replicates} replicates)'
    )

    manifest_rows: list[dict[str, Any]] = []
    for cell in cells:
        config = render_config(template, cell, args.max_job_time_min, job_definition, queue_prefix=args.queue_prefix)
        if args.dry_run:
            print(f'--- {cell.cell_id} (vcpu={cell.vcpu} memory_mb={cell.memory_mb}) ---')
            print(json.dumps(config['submission_arg_overrides']))
            continue
        gt_id = submit_cell(config, args.template.resolve().parent)
        print(f'{cell.cell_id}: general_task_id={gt_id}')
        manifest_rows.append(
            {
                **asdict(cell),
                'cell_id': cell.cell_id,
                'job_queue': queue_for(cell, args.queue_prefix),
                'general_task_id': gt_id,
            }
        )

    if args.dry_run:
        return 0

    manifest = {
        'submitted_at': dt.datetime.now(dt.UTC).isoformat(),
        'queue_prefix': args.queue_prefix,
        'rows': manifest_rows,
    }
    args.manifest.write_text(json.dumps(manifest, indent=2))
    print(f'wrote manifest: {args.manifest} ({len(manifest_rows)} submits)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
