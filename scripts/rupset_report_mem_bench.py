#!/usr/bin/env python
"""Benchmark the JVM heap a rupture-set *report* needs, locally, to size AWS Batch memory.

Why this exists
---------------
Rupture-set report jobs (``runzi reports rupset``) OOM on AWS Batch
(``java.lang.OutOfMemoryError: Java heap space``) while running fine locally. The reason is a
heap mismatch, not a container OOM-kill:

  * On **AWS Batch** the JVM heap is *derived* from the container memory reservation:
    ``-Xmx = ecs_memory/1000 - 2`` GB (``runzi/aws/aws.py``, ``get_ecs_job_config``). The task ships
    ``ecs_memory=7000`` -> ``-Xmx5G``, which is the heap that OOMs.
  * ``default_submission_args.jvm_heap_max`` (=32) is **ignored on AWS** -- it only feeds the
    LOCAL/CLUSTER bash launcher (``opensha_task_factory.py``), which is why the same report survives
    locally at ``-Xmx32G``.

Heap demand for a report is the same OpenSHA code and the same rupture-set input regardless of
platform, so **measuring the heap locally is a valid proxy for the Batch requirement** -- and it is
cheap: no AWS round-trip.

What it does
------------
For a given rupture-set toshi ID and report level (default ``FULL`` -- the heaviest), it runs the
report locally several times at different heap ceilings and records, per run:

  * **peak occupancy** -- the high-water used-heap just before a GC (from a GC log), and
  * **live set** -- used heap *after* a Full GC (the true floor of live data), and
  * whether the run **completed** or **OOM'd**.

It drives the real ``RupsetReportJobRunner`` -> ``build_tasks`` path (so the launcher, config, and
Java entry point are exactly production's), setting the per-run ``-Xmx`` through the existing
``submission_arg_overrides`` mechanism (locally ``-Xmx == jvm_heap_max``). GC logging is enabled with
zero code changes by exporting ``JAVA_TOOL_OPTIONS`` before launch -- the JVM picks it up and the
command-line ``-Xmx`` still wins for the ceiling.

Two things make each run *faithful to AWS Batch*:

  * **Cold run** -- ``ReportPageGen`` skips plots whose output already exists ("Already have plot ..."),
    so a warm report dir makes reruns cheap and their heap numbers meaningless. Each run first *clears*
    the report output dir, exactly like a fresh Batch container.
  * **Headless** -- ``-Djava.awt.headless=true`` forces the same AWT/Java2D rendering path Batch uses
    (no X server), so the number does not depend on the local ``$DISPLAY``.

Two phases:

  1. **Estimate** -- one run at a generous ceiling (``--estimate-xmx``, default 32G) to observe peak
     occupancy without OOM pressure.
  2. **Floor sweep** -- reruns at a descending ``--xmx-list`` (default ``16,12,10,8,6,5``), marking
     each OK/OOM. The **floor** is the smallest ``-Xmx`` that completes without OOM; ``5G`` (current
     prod) is included to reproduce the failure. Each cell is a *full report*, so trim the list if a
     run is slow.

Output: a CSV (``--csv``, default ``scripts/rupset_report_mem_results.csv``) and a printed
recommendation:

  * ``recommended_xmx  = max(ceil(floor * 1.3), ceil(live_set_gb * 1.5))``  (headroom above the
    measured floor, cross-checked against live data), and
  * ``recommended_ecs_memory = ceil_to_1000((recommended_xmx + 2) * 1000)``  -- reversing the AWS
    ``ecs_memory/1000 - 2`` formula. Put this into ``ecs_memory`` on the task's
    ``default_submission_args`` (that is the lever that reaches Batch).

Prerequisites (already required for any local OpenSHA run): ``NZSHM22_FATJAR``, ``NZSHM22_OPENSHA_JRE``,
``NZSHM22_SCRIPT_WORK_PATH``, and toshi access (``NZSHM22_TOSHI_API_ENABLED`` + URL/key or Cognito
login) to fetch the rupture-set file.

Usage::

    # Dry run: print what would be executed, no JVM launches.
    python scripts/rupset_report_mem_bench.py <rupture_set_id> --dry-run

    # Measure a single rupture set at FULL (estimate + full floor sweep).
    python scripts/rupset_report_mem_bench.py <rupture_set_id>

    # Cheaper: skip the estimate, test just two ceilings.
    python scripts/rupset_report_mem_bench.py <rupture_set_id> --estimate-xmx 0 --xmx-list 8,6
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

# GC pause summary lines look like ``... 4096M->512M(8192M) 12.3ms``; the unit letter is adaptive
# (K/M/G) so we normalise to MB. before = occupancy at GC start, after = occupancy at GC end.
_GC_UNIT_MB = {'K': 1.0 / 1024.0, 'M': 1.0, 'G': 1024.0}
_GC_RE = re.compile(r'(\d+)([KMG])->(\d+)([KMG])\((\d+)([KMG])\)')
_PAUSE_FULL = 'Pause Full'
# Match the JVM's own message, which carries the ``java.lang.`` prefix -- NOT the bare word inside our
# ``-XX:+ExitOnOutOfMemoryError`` flag, which the JVM echoes in a "Picked up JAVA_TOOL_OPTIONS" line.
_OOM_MARKER = 'java.lang.OutOfMemoryError'
_JAVA_TOOL_OPTIONS_ECHO = 'Picked up JAVA_TOOL_OPTIONS'

DEFAULT_XMX_LIST = (16, 12, 10, 8, 6, 5)
DEFAULT_ESTIMATE_XMX = 32
DEFAULT_REPORT_LEVEL = 'FULL'
DEFAULT_CSV = Path(__file__).with_name('rupset_report_mem_results.csv')


@dataclass
class RunResult:
    """One report run at a fixed heap ceiling."""

    rupture_set_id: str
    report_level: str
    xmx_gb: int
    status: str  # OK | OOM | FAILED
    peak_occupancy_mb: int | None
    live_set_mb: int | None
    wall_sec: float


def parse_gc_log(path: Path) -> tuple[int | None, int | None]:
    """Return ``(peak_occupancy_mb, live_set_mb)`` from a unified-logging GC file.

    peak occupancy = max used heap *before* any GC (the high-water demand); live set = max used heap
    *after* a Full GC (the largest live-data set that survived a full collection -- the real floor a
    heap must hold). Returns ``None`` for a value we could not observe (e.g. no Full GC happened).
    """
    if not path.exists():
        return None, None
    peak: float | None = None
    live_after_full: float | None = None
    for line in path.read_text().splitlines():
        match = _GC_RE.search(line)
        if not match:
            continue
        before = int(match.group(1)) * _GC_UNIT_MB[match.group(2)]
        after = int(match.group(3)) * _GC_UNIT_MB[match.group(4)]
        peak = before if peak is None else max(peak, before)
        if _PAUSE_FULL in line:
            live_after_full = after if live_after_full is None else max(live_after_full, after)
    return (
        round(peak) if peak is not None else None,
        round(live_after_full) if live_after_full is not None else None,
    )


def _oom_messages(combined_output: str) -> list[str]:
    """The actual ``java.lang.OutOfMemoryError...`` lines from the output (empty if none).

    Skips the ``Picked up JAVA_TOOL_OPTIONS`` echo, which contains the literal ``OutOfMemoryError`` from
    our ``-XX:+ExitOnOutOfMemoryError`` flag and is not an actual OOM.
    """
    return [
        line.strip()
        for line in combined_output.splitlines()
        if _OOM_MARKER in line and _JAVA_TOOL_OPTIONS_ECHO not in line
    ]


def _classify(returncode: int, combined_output: str) -> str:
    """Classify a run from the JVM's own OutOfMemoryError message (not incidental substrings).

    Distinguishes OOM *kinds*, because only a ``Java heap space`` / ``GC overhead`` OOM is fixable by
    raising ``-Xmx`` / ``ecs_memory``. A native-thread, ``Requested array size``, or direct-buffer OOM is
    not a sizing problem -- a bigger container would not help (and a bigger heap makes native OOM worse).
    """
    oom = ' | '.join(_oom_messages(combined_output))
    if oom:
        if 'Java heap space' in oom or 'GC overhead limit exceeded' in oom:
            return 'HEAP_OOM'
        if 'unable to create' in oom or 'native thread' in oom:
            return 'NATIVE_OOM'
        if 'Requested array size' in oom:
            return 'ARRAY_OOM'
        if 'Direct buffer memory' in oom:
            return 'DIRECT_OOM'
        return 'OOM_OTHER'
    return 'OK' if returncode == 0 else 'FAILED'


def _error_signature(combined_output: str) -> list[str]:
    """Pull the diagnostic lines out of a failing run's output (OOM message, exceptions, causes)."""
    keys = ('OutOfMemoryError', 'Exception', 'Caused by', 'Error:', 'Traceback', 'Py4J', 'at ')
    hits = [
        line.rstrip()
        for line in combined_output.splitlines()
        if any(k in line for k in keys) and _JAVA_TOOL_OPTIONS_ECHO not in line
    ]
    # De-dup while preserving order, cap the volume.
    seen: set[str] = set()
    out: list[str] = []
    for line in hits:
        if line not in seen:
            seen.add(line)
            out.append(line)
    return out[:25]


def run_once(
    rupture_set_id: str,
    report_level: str,
    xmx_gb: int,
    gc_dir: Path,
    dry_run: bool,
) -> RunResult:
    """Build the LOCAL report task at ``-Xmx{xmx_gb}G`` and run it, capturing heap + status.

    Imports runzi lazily: ``NZSHM22_REPORT_LEVEL`` must be in the environment *before* the runner
    module binds ``REPORT_LEVEL`` at import time, and the caller sets it before the first call.
    """
    import runzi.automation.local_config as local_config
    from runzi.arguments import ArgSweeper
    from runzi.automation.local_config import ClusterModeEnum
    from runzi.build_tasks import build_tasks
    from runzi.tasks.rupset_report import RupsetReportArgs, RupsetReportJobRunner

    # Local, and never create a toshi general task or upload the report -- this is a measurement.
    local_config.CLUSTER_MODE = ClusterModeEnum.LOCAL
    local_config.USE_API = False

    prototype = RupsetReportArgs(source_solution_id=rupture_set_id, build_report_level=None)
    job_input = ArgSweeper(prototype_args=prototype, swept_args={}, title="", description="")
    runner = RupsetReportJobRunner(job_input)
    # Drive the per-run heap ceiling through the supported override path (locally -Xmx == jvm_heap_max).
    runner.argument_sweeper.submission_arg_overrides = {'jvm_heap_max': xmx_gb}

    submission_args = runner.set_submission_args()
    model_type = runner.get_model_type()
    scripts = list(
        build_tasks(runner.argument_sweeper, submission_args, runner.task_module, model_type, runner.job_name, None)
    )
    if not scripts:
        raise RuntimeError(f'no task script produced for {rupture_set_id!r} -- is it a valid rupture-set id?')
    if len(scripts) > 1:
        print(f'  note: {rupture_set_id!r} expanded to {len(scripts)} tasks; benchmarking the first only')
    script_path = str(scripts[0])

    # %p (PID) keeps the file distinct even if the JVM forks; the launcher's -Xmx still wins the ceiling.
    # headless=true forces the same AWT/Java2D path AWS Batch uses (no X server), so the measured heap
    # is faithful and independent of the local $DISPLAY.
    gc_file = f'{gc_dir}/gc.{rupture_set_id}.{xmx_gb}g.%p.log'
    java_tool_options = f'-Xlog:gc*:file={gc_file}:time,level,tags -XX:+ExitOnOutOfMemoryError -Djava.awt.headless=true'

    # ReportPageGen skips plots whose output files already exist ("Already have plot ..."), so a warm
    # report dir makes reruns cheap and the heap number meaningless. Clear it: every run is a *cold* run,
    # exactly like an AWS Batch container, which always starts empty.
    report_dir = Path(local_config.WORK_PATH) / rupture_set_id / 'DiagnosticsReport'

    if dry_run:
        print(f'  [dry-run] xmx={xmx_gb}G  script={script_path}')
        print(f'            would clear (cold run): {report_dir}')
        print(f'            JAVA_TOOL_OPTIONS={java_tool_options}')
        return RunResult(rupture_set_id, report_level, xmx_gb, 'OK', None, None, 0.0)

    shutil.rmtree(report_dir, ignore_errors=True)

    # Snapshot existing java worker logs so we can find the one this run creates (port is random). The
    # worker's stdout (report progress, and any Java stack trace) goes to that file, not to our stderr.
    work_path = Path(local_config.WORK_PATH)
    before_logs = set(work_path.glob('java_app.*.log'))

    env = dict(os.environ, JAVA_TOOL_OPTIONS=java_tool_options)
    started = time.monotonic()
    proc = subprocess.run(['bash', script_path], env=env, capture_output=True, text=True)
    wall_sec = time.monotonic() - started

    new_logs = sorted(set(work_path.glob('java_app.*.log')) - before_logs, key=lambda p: p.stat().st_mtime)
    java_log_text = new_logs[-1].read_text(errors='replace') if new_logs else ''
    completed_marker = 'DONE building report' in java_log_text

    combined = proc.stdout + proc.stderr + java_log_text
    status = _classify(proc.returncode, combined)
    # A clean exit that never reached the completion marker is a silent failure, not a success.
    if status == 'OK' and new_logs and not completed_marker:
        status = 'FAILED'

    # Persist the full output for every run so a failure can always be inspected after the fact.
    out_path = gc_dir / f'run.{rupture_set_id}.{xmx_gb}g.out'
    out_path.write_text(combined)

    # The GC file carries the real PID; glob for it (there is exactly one JVM per run).
    gc_files = sorted(gc_dir.glob(f'gc.{rupture_set_id}.{xmx_gb}g.*.log'), key=lambda p: p.stat().st_mtime)
    peak_mb, live_mb = parse_gc_log(gc_files[-1]) if gc_files else (None, None)

    print(
        f'  xmx={xmx_gb:>3}G  status={status:<8}  '
        f'peak={peak_mb if peak_mb is not None else "-"}MB  '
        f'live_set={live_mb if live_mb is not None else "-"}MB  wall={wall_sec:.0f}s'
    )
    if status != 'OK':
        for message in _oom_messages(combined):
            print(f'    OOM: {message}')
        signature = _error_signature(combined)
        if signature:
            print('    error signature:')
            for line in signature:
                print(f'      {line}')
        print(f'    full output saved to: {out_path}')
    return RunResult(rupture_set_id, report_level, xmx_gb, status, peak_mb, live_mb, wall_sec)


def ceil_to(value: float, step: int) -> int:
    """Round ``value`` up to the next multiple of ``step``."""
    return int(math.ceil(value / step) * step)


def recommend(results: list[RunResult]) -> dict[str, object]:
    """Derive a recommended -Xmx and ecs_memory from the sweep results for one rupture set."""
    ok = [r for r in results if r.status == 'OK']
    floor = min((r.xmx_gb for r in ok), default=None)

    # Prefer the live set observed at the tightest OK heap (a Full GC is most likely under pressure);
    # fall back to the largest peak occupancy seen anywhere.
    floor_row = min(ok, key=lambda r: r.xmx_gb) if ok else None
    live_gb = (floor_row.live_set_mb / 1024.0) if (floor_row and floor_row.live_set_mb) else None
    peak_mb = max((r.peak_occupancy_mb for r in results if r.peak_occupancy_mb), default=None)
    peak_gb = (peak_mb / 1024.0) if peak_mb else None

    if floor is None:
        return {
            'floor_gb': None,
            'recommended_xmx_gb': None,
            'recommended_ecs_memory_mb': None,
            'live_gb': live_gb,
            'peak_gb': peak_gb,
        }

    candidates = [math.ceil(floor * 1.3)]
    if live_gb:
        candidates.append(math.ceil(live_gb * 1.5))
    recommended_xmx = max(candidates)
    recommended_ecs_memory = ceil_to((recommended_xmx + 2) * 1000, 1000)
    return {
        'floor_gb': floor,
        'recommended_xmx_gb': recommended_xmx,
        'recommended_ecs_memory_mb': recommended_ecs_memory,
        'live_gb': live_gb,
        'peak_gb': peak_gb,
    }


def write_csv(path: Path, results: list[RunResult]) -> None:
    fields = ['rupture_set_id', 'report_level', 'xmx_gb', 'status', 'peak_occupancy_mb', 'live_set_mb', 'wall_sec']
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for result in results:
            row = asdict(result)
            row['wall_sec'] = round(row['wall_sec'], 1)
            writer.writerow(row)


def check_prerequisites() -> list[str]:
    """Return a list of human-readable problems with the local OpenSHA/toshi setup (empty == ok)."""
    from runzi.automation.local_config import FATJAR, OPENSHA_JRE, USE_API, WORK_PATH

    problems: list[str] = []
    if not Path(FATJAR).exists():
        problems.append(f'NZSHM22_FATJAR does not exist: {FATJAR}')
    if not Path(OPENSHA_JRE).exists():
        problems.append(f'NZSHM22_OPENSHA_JRE does not exist: {OPENSHA_JRE}')
    if not Path(WORK_PATH).exists():
        problems.append(f'NZSHM22_SCRIPT_WORK_PATH does not exist: {WORK_PATH}')
    if not USE_API:
        problems.append('NZSHM22_TOSHI_API_ENABLED is not set; toshi access is needed to fetch the rupture set')
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('rupture_set_ids', nargs='+', help='One or more rupture-set toshi IDs (benchmarked in turn).')
    parser.add_argument('--report-level', default=DEFAULT_REPORT_LEVEL, help='LIGHT | DEFAULT | FULL (default FULL).')
    parser.add_argument(
        '--xmx-list',
        default=','.join(str(x) for x in DEFAULT_XMX_LIST),
        help='Comma-separated descending -Xmx (GB) sweep. Each is a full report; trim if slow.',
    )
    parser.add_argument(
        '--estimate-xmx',
        type=int,
        default=DEFAULT_ESTIMATE_XMX,
        help='Generous -Xmx (GB) for the no-pressure estimate run; 0 to skip.',
    )
    parser.add_argument('--csv', type=Path, default=DEFAULT_CSV, help='Where to write the results CSV.')
    parser.add_argument('--dry-run', action='store_true', help='Print planned runs without launching the JVM.')
    args = parser.parse_args(argv)

    # Must be set before importing the runner (it binds REPORT_LEVEL at import time).
    os.environ['NZSHM22_REPORT_LEVEL'] = args.report_level

    from runzi.automation.local_config import WORK_PATH

    if not args.dry_run:
        problems = check_prerequisites()
        if problems:
            print('cannot run benchmark:', file=sys.stderr)
            for problem in problems:
                print(f'  - {problem}', file=sys.stderr)
            return 1

    gc_dir = Path(WORK_PATH) / 'gc_logs'
    gc_dir.mkdir(parents=True, exist_ok=True)

    sweep = [int(x) for x in args.xmx_list.split(',') if x.strip()]
    # Estimate ceiling first (if enabled and not already in the sweep), then the descending floor sweep.
    ceilings: list[int] = []
    if args.estimate_xmx and args.estimate_xmx not in sweep:
        ceilings.append(args.estimate_xmx)
    ceilings.extend(sorted(sweep, reverse=True))

    all_results: list[RunResult] = []
    for rupture_set_id in args.rupture_set_ids:
        print(f'\n=== {rupture_set_id}  (report level {args.report_level}) ===')
        results = [run_once(rupture_set_id, args.report_level, xmx, gc_dir, args.dry_run) for xmx in ceilings]
        all_results.extend(results)

        if args.dry_run:
            continue

        rec = recommend(results)
        print(f'  --- recommendation for {rupture_set_id} ---')
        if rec['recommended_ecs_memory_mb'] is None:
            print(f'    every ceiling OOM\'d (min tested {min(ceilings)}G). Raise --xmx-list and rerun.')
        else:
            live = f'{rec["live_gb"]:.1f}G' if rec['live_gb'] else 'n/a'
            peak = f'{rec["peak_gb"]:.1f}G' if rec['peak_gb'] else 'n/a'
            print(f'    heap floor (smallest OK -Xmx): {rec["floor_gb"]}G   live set: {live}   peak occupancy: {peak}')
            print(f'    recommended -Xmx:        {rec["recommended_xmx_gb"]}G')
            print(
                f'    recommended ecs_memory:  {rec["recommended_ecs_memory_mb"]} MB'
                f'  (== -Xmx {rec["recommended_xmx_gb"]}G via ecs_memory/1000 - 2)'
            )

    if not args.dry_run:
        write_csv(args.csv, all_results)
        print(f'\nwrote {len(all_results)} rows to {args.csv}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
