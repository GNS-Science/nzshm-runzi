# EC2 job-sizing benchmark for crustal inversions (#323, Phase 1)

Benchmarks the cost/performance of different **job sizes** (vCPU × memory) for crustal inversions on
the existing EC2 Batch compute environment (`runzi-ec2-CE`, `["optimal"]` +
`BEST_FIT_PROGRESSIVE` — see [ADR-0008](../../docs/architecture/adr/0008-aws-batch-ec2-compute-environment.md)).
No Terraform/infra changes: it only submits jobs with per-cell `submission_arg_overrides`.

## What it measures

Crustal inversions are **time-bounded** (`max_inversion_time`), so wall time is held constant and the
throughput signal is **anneal iterations completed** in that time. The anneal thread count
(`selector_threads × averaging_threads` = 16) is **fixed** across all cells, so 4- and 8-vCPU cells
deliberately oversubscribe — the benchmark prices the tradeoff of under- vs fully-provisioning cores
for the standard 16-thread inversion. Cost is attributed per job from the **actual EC2 instance type
Batch placed it on** (read back via the Batch/ECS/EC2 APIs), pro-rated per vCPU.

Matrix: vCPU {4, 8, 16} × memory:vCPU ratio {2:1→C, 4:1→M, 8:1→R} × 3 replicates = 27 submits. The
ratio is *intended* to nudge which "optimal" family Batch picks, but this is weak in practice — a pilot
2:1 (compute-optimized) request landed on `m6i.xlarge` (a 4:1 general-purpose box). Also note "optimal"
resolves to **current-gen** families (m6i/c6i/r6i, m5/c5/r5), not the legacy C4/M4/R4. Either way the
analysis uses the instance each job **actually** landed on (read back from Batch/ECS/EC2), so family
targeting being approximate doesn't distort the results.

The iteration count is **not** in the CloudWatch log — the inversion uploads it in its
`java_app.<port>.log` task file to Toshi, so `collect_results.py` fetches and parses that log per cell
(joined to Batch cost data by `general_task_id`). From that one log it reads **iterations**
(`Total Iterations:`), **perturbations** (`Total Perturbations:`), and **final energy** (the `Total:`
value under the last `Best energy:` block — the true solution-quality signal, lower = better).

## Prerequisites

- AWS credentials + toshi API configured (same as any `runzi --cluster-mode AWS` run).
- For the **cost** columns, the caller's role needs `ecs:DescribeContainerInstances` + `ec2:DescribeInstances`
  (added to the `runzi-admin` access tier in `terraform/access/main.tf`; a deployer must apply it). Without
  them the collector still reports iterations/perturbations/energy and just leaves cost blank.
- The **crustal rupture set** is baked into `crustal_inversion.template.json`
  (`rupture_set_id: RmlsZToxMDAwNjk=`); edit that file to change it.
- Refresh the price table in `collect_results.py` (`INSTANCE_SPECS`, `# last verified:` marker) before
  trusting cost figures.
- Jobs target the **`runzi-ec2-experimental-JD`** (`:experimental` image) by default, so the benchmark
  runs the latest-built worker; pass `--prod` to use `runzi-ec2-JD` instead. A stale image manifests as
  a py4j `127.0.0.1:None` gateway error (the worker predates the `NZSHM22_APP_PORT` gateway change) —
  rebuild/promote that tag if you hit it.

## Workflow

```bash
# 0. Dry run — confirm the 27 cells render valid EC2-targeted configs (no AWS calls).
uv run python scripts/ec2_sizing/submit_matrix.py --dry-run

# 1. PILOT (the key risk): ONE short cell (--limit 1) to confirm the job runs AND the iteration regex.
uv run python scripts/ec2_sizing/submit_matrix.py \
    --limit 1 --max-inversion-time 2 --manifest scratch/pilot.json
#   ...wait for the job to finish, then run the collector on the pilot manifest:
uv run python scripts/ec2_sizing/collect_results.py --manifest scratch/pilot.json --csv scratch/pilot.csv
#   If `iterations` is empty/wrong, the default regex didn't match the java_app log. Grab the actual
#   iteration line from that log (e.g. via toshi, or the downloaded copy) and pass --iteration-regex
#   (group 1 = the integer) on the real collect. Fallback: re-enable a getSolutionMetrics call upstream.

# 2. Full run — 27 submits at the fixed inversion time (default 10 min).
uv run python scripts/ec2_sizing/submit_matrix.py --manifest scripts/ec2_sizing/manifest.json
#   Under one BEST_FIT_PROGRESSIVE "optimal" CE, Batch converges on ONE instance type for the whole
#   queue (a full run landed every cell on r6i.12xlarge, driven by the memory-heavy 8:1 R cells). To
#   let "optimal" pick lighter c/m families, drop the 8:1 cells:  --ratios C M

# 3. Collect + analyse once the jobs finish (terminal Batch jobs age out ~24h — collect promptly).
uv run python scripts/ec2_sizing/collect_results.py \
    --manifest scripts/ec2_sizing/manifest.json --csv scripts/ec2_sizing/results.csv \
    [--iteration-regex '<pattern with group 1 = the integer>']
```

`collect_results.py` writes a per-job CSV and prints a per-cell summary ranked by iterations-per-dollar.
Sanity-check that every job's `duration_sec` ≈ the inversion time (confirms the time-bound held) and
that no job stuck in `RUNNABLE` (an oversized memory request that no `"optimal"` instance can satisfy).

## Files

- `crustal_inversion.template.json` — base config (fixed 16 threads, `max_inversion_time: 10.0`);
  `submit_matrix.py` injects per-cell sizing.
- `submit_matrix.py` — renders + submits the matrix, writes `manifest.json`.
- `collect_results.py` — joins the manifest to live Batch/EC2/log data → CSV + summary.
- Reusable helper: `runzi.aws.batch_query.instance_type_by_job_id` (which instance ran each job).

## Non-goals

Instance-type *pinning* (Graviton/arm64, Spot vs On-Demand) is the direct #323 "instance types"
question and needs a deployer Terraform apply — a follow-up only if these sizing results are ambiguous.
Acting on the results (changing the CE's `instance_types` or the crustal default `SubmissionArgs`) is
an architecture change and gets its own ADR.
