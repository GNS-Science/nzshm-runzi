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

---

# EC2 job-sizing benchmark for the coulomb rupture-set builder

Same idea, different task and **different metric**. The coulomb builder (`runzi rupset coulomb`) runs
**to completion** (~20 min), so wall time is the signal, not throughput: we ask *how fast / how cheaply
does a build finish, and where do extra cores stop paying?* This is a strict subtraction from the
inversion collector — wall time comes straight off the Batch job summary, so there is **no Toshi log to
parse** (no `--iteration-regex`).

## What it measures

- **Cores.** vCPU `{4, 8, 16, 32}` with **`num_cores` pinned to `ecs_vcpu`** per cell (the builder
  calls `setNumThreads(num_cores)`), so each cell actually uses the cores it pays for and the
  wall-time-vs-cores curve is meaningful. We do *not* know a priori whether the builder parallelizes —
  the curve answers it: falling wall time ⇒ it scales (pick the knee); flat ⇒ it doesn't (run smallest).
- **Instance family.** `c6a` (compute-optimized) vs `m6a` (general purpose), both AMD (cheapest x86),
  **pinned** via per-family Batch queues from `terraform/ec2-sizing-benchmark/`. `ecs_memory` is sized to
  ~fill each family's per-vCPU RAM (c ≈ 1.8 GB/vCPU, m ≈ 3.8 GB/vCPU), so a c-family **OOM is the finding**
  that the build needs more than 2 GB/vCPU and must run on m-family.

Cost is the same fair-share `(instance $/hr / instance vCPU) × job vCPU × wall-hours`, priced from the
instance Batch placed each job on. The summary ranks cells by **mean cost per build** (cheapest first)
with **mean wall seconds** alongside, so the cost knee and time knee are visible together.

## Workflow

```bash
# 0. Dry run — confirm the 16 cells render valid EC2-targeted configs (no AWS calls).
uv run python scripts/ec2_sizing/submit_coulomb_matrix.py --dry-run --queue-prefix ec2sizing

# 1. Stand up the pinned per-family queues (once): from terraform/ec2-sizing-benchmark/ with
#    instance_types = ["c6a","m6a"] (bare family names → any size in the family, so vCPU can sweep).
#    NB: VERIFY AWS Batch accepts bare family names; if a plan/apply rejects them, fall back to
#    enumerating sizes: ["c6a.xlarge","c6a.2xlarge","c6a.4xlarge","c6a.8xlarge", + the m6a set].
#    `terraform output queues` prints {family -> queue}; name_prefix defaults to "ec2sizing".

# 2. PILOT (the key risk): ONE cell to confirm the deployed :experimental worker isn't stale (#323 hit a
#    py4j 127.0.0.1:None from an out-of-date image) AND that the wall-clock path works end-to-end.
uv run python scripts/ec2_sizing/submit_coulomb_matrix.py \
    --limit 1 --queue-prefix ec2sizing --manifest scratch/coulomb_pilot.json
#    ...wait for the job to finish, then:
uv run python scripts/ec2_sizing/collect_coulomb_results.py \
    --manifest scratch/coulomb_pilot.json --csv scratch/coulomb_pilot.csv
#    A real duration_sec (and a priced cost, if you have the ECS/EC2 read perms) proves the pipeline.

# 3. Full matrix — 16 submits (2 families × 4 vCPU × 2 replicates).
uv run python scripts/ec2_sizing/submit_coulomb_matrix.py \
    --queue-prefix ec2sizing --manifest scripts/ec2_sizing/coulomb_manifest.json

# 4. Collect + analyse once the jobs finish (terminal Batch jobs age out ~24h — collect promptly).
uv run python scripts/ec2_sizing/collect_coulomb_results.py \
    --manifest scripts/ec2_sizing/coulomb_manifest.json --csv scripts/ec2_sizing/coulomb_results.csv
#    Cost needs no ECS read-back for a pinned run: the instance is derived from family + vCPU, and the
#    fair-share per-vCPU rate is identical across sizes within a family. So even after the pinned CEs
#    scale to zero (ECS can no longer resolve the instance), re-running the collector still prices every
#    cell. (--instance-type is only for an *unpinned* run whose CE has scaled to zero.)
```

Then `terraform destroy` the benchmark module (the shared `runzi-ec2-CE` is untouched). Each build
uploads a real rupture set to Toshi (`USE_API` is required to mint the `general_task_id` that links back
to the Batch job) — note the ~16 throwaway uploads for cleanup.

## Coulomb files

- `coulomb_rupture_set.template.json` — base config (fault model `CFM_1_0A_DOM_SANSTVZ`, `max_sections`
  2000); `submit_coulomb_matrix.py` injects per-cell `ecs_vcpu` / `num_cores` / `ecs_memory`.
- `submit_coulomb_matrix.py` — renders + submits the family × vCPU matrix, writes `coulomb_manifest.json`.
- `collect_coulomb_results.py` — joins the manifest to live Batch/EC2 data → CSV + summary (wall time +
  cost, no Toshi).
- `_cost.py` — the EC2 price table + fair-share cost formula, shared with the inversion collector.

---

# EC2 job-sizing benchmark for OpenQuake hazard (#344)

Same idea again — run-to-completion, **wall-clock metric** — for the OpenQuake hazard task
(`runzi hazard oq_hazard`). See [the findings doc](../../docs/benchmarks/ec2-sizing-oq-hazard.md).

**Like coulomb, OQ needs its core budget pinned (#344).** OpenQuake sizes its processpool to the cores it
*detects*; on EC2 the container sees the **host's** cores (Batch uses CPU shares, not cpuset), so without a
cap OQ spawns a worker per host core and OOM-kills the memory-limited container (`oq engine --run` exits
`-9`). So each cell ships **`num_cores = vcpu`** — the OQ task feeds it to `execute_openquake`, which
writes it to `openquake.cfg` `[distribution] num_cores`. The matrix is family × vCPU; `render_config`
injects `ecs_vcpu` / `num_cores` (= vcpu) / `ecs_memory` / `ecs_job_definition` / `ecs_max_job_time_min`.

## What it measures

- **Cores.** vCPU `{4, 8, 16, 32}`; falling wall time ⇒ hazard scales (pick the knee), flat ⇒ it doesn't
  (run smallest). (EC2 is also what unlocks > 16 vCPU — Fargate, hazard's current default, caps there.)
- **Instance family.** `c6a` (compute-optimized) vs `m6a` (general purpose), both AMD, **pinned** via
  per-family Batch queues. `ecs_memory` fills each family's per-vCPU RAM (c ≈ 1.8, m ≈ 3.8 GB/vCPU), so a
  c-family **OOM is the finding** that hazard needs more than 2 GB/vCPU. Add `--families r6a` (7.6 GB/vCPU)
  if the c/m cells OOM.

## The test workload

`oq_hazard.template.json` pairs the **full 2022 GMCM logic tree** (from `NSHM_v1.0.4`, ⇒ 21 gsims) with a
**single SRM branch** — `srm_single_branch_TEST.json`, committed next to the template so its relative path
resolves (`submit_oq_hazard_matrix.py` writes each cell's temp config into the template's directory for
exactly this reason). A single-branch SRM is essential: the runner explodes the SRM logic tree into **one
Batch job per branch**, and the collector assumes one submit → one job. Sites are the NZ 0.2° grid
(`NZ_0_2_NB_1_1`, ~1057) — raised ~4× from the original `SRWG214`+`NZ` (~250) after a 4-vCPU pilot ran
~1521 s, so fixed serial overhead (OQ startup, source-model build, export/store) stays a small fraction of
wall time in the **high-vCPU** cells rather than flattening the scaling curve. Sites are the cleanest
parallel axis in classical PSHA; tune IMTs/sites from the pilot if the low-vCPU cell nears the 240-min
limit or a low-memory (c-family) cell OOMs.

## Required first: stand up the pinned per-family queues

The family axis only works if each cell is **pinned** to a compute environment locked to one instance
family. You cannot get that from the shared `runzi-ec2-CE`: it runs `BEST_FIT_PROGRESSIVE` over
`["c6a","m6a","c6i","m6i"]` (ADR-0011), so a mixed queue collapses every cell onto whichever type fits
cheapest and the family column becomes meaningless (this is what happened to #341 — everything landed on
`r6i`). So before the pilot, apply `terraform/ec2-sizing-benchmark/` to create one CE + one queue
(`{name_prefix}-{family}-Q`) per family. The module is task-agnostic — **no module change** — but run it in
a **separate Terraform workspace** so the OQ queues don't collide with a concurrent coulomb run that shares
the same `name_prefix`:

```bash
cd terraform/ec2-sizing-benchmark
terraform workspace new oq-hazard            # isolate this run's state
terraform apply                              # with instance_types = ["c6a","m6a"]
terraform output queues                      # prints {family -> queue}; name_prefix defaults to "ec2sizing"
```

(See that module's README re: whether AWS Batch accepts bare family names `["c6a","m6a"]` or needs
enumerated sizes.) Tear it down after collecting: `terraform destroy` then `terraform workspace delete
oq-hazard`; the shared `runzi-ec2-CE` is untouched throughout.

The only run that skips this is an **unpinned smoke test**: omit `--queue-prefix` below and cells go to the
JD-derived `runzi-ec2-Q` on the shared CE — fine to confirm a hazard job runs and the collect path works,
but Batch picks the instance so you can't compare families.

## Workflow

```bash
# 0. Dry run — confirm the 16 cells render valid EC2-targeted configs (no AWS calls, no num_cores).
uv run python scripts/ec2_sizing/submit_oq_hazard_matrix.py --dry-run --queue-prefix ec2sizing

# 1. PILOT (the key risk): ONE cell to confirm the wall-clock path end-to-end AND to time the workload
#    (tune imts/locations in the template if it's too short/long before spending the full matrix).
uv run python scripts/ec2_sizing/submit_oq_hazard_matrix.py \
    --limit 1 --queue-prefix ec2sizing --manifest scratch/oq_hazard_pilot.json
#    ...wait for the job to finish, then:
uv run python scripts/ec2_sizing/collect_oq_hazard_results.py \
    --manifest scratch/oq_hazard_pilot.json --csv scratch/oq_hazard_pilot.csv

# 2. Full matrix — 16 submits (2 families × 4 vCPU × 2 replicates).
uv run python scripts/ec2_sizing/submit_oq_hazard_matrix.py \
    --queue-prefix ec2sizing --manifest scripts/ec2_sizing/oq_hazard_manifest.json

# 3. Collect + analyse once the jobs finish (terminal Batch jobs age out ~24h — collect promptly).
uv run python scripts/ec2_sizing/collect_oq_hazard_results.py \
    --manifest scripts/ec2_sizing/oq_hazard_manifest.json --csv scripts/ec2_sizing/oq_hazard_results.csv
#    As with coulomb, a pinned run needs no ECS read-back: the instance is derived from family + vCPU.
```

After collecting, tear down the benchmark queues (see above); the shared `runzi-ec2-CE` is
untouched. Each submit uploads the single-branch SRM (and, per-cell, mints a `general_task_id`) to Toshi —
note the ~16 throwaway uploads for cleanup, plus one SRM logic-tree file per cell.

## OQ hazard files

- `oq_hazard.template.json` — base config (full 2022 GMCM × single SRM branch, ~250 sites);
  `submit_oq_hazard_matrix.py` injects per-cell `ecs_vcpu` / `num_cores` (= vcpu, → OQ num_cores) / `ecs_memory`.
- `srm_single_branch_TEST.json` — the single-branch SRM, co-located so the template's relative path resolves.
- `submit_oq_hazard_matrix.py` — renders + submits the family × vCPU matrix, writes `oq_hazard_manifest.json`.
- `collect_oq_hazard_results.py` — joins the manifest to live Batch/EC2 data → CSV + summary (wall time +
  cost, no Toshi). Self-contained, sharing only `_cost.py`. Also reads each job's CloudWatch log for the
  `Using N processpool workers` line (`oq_cores` column) and flags any cell where it ≠ vCPU — proof the
  num_cores cap took; a flagged cell's wall time is invalid.
