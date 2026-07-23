# EC2 job-sizing benchmark — OpenQuake hazard

> **Status: tooling landed, run pending.** This document defines the method and holds the results table;
> the *Results / Findings / Recommendation / Applied* sections are filled in after an operator runs the
> matrix (see `scripts/ec2_sizing/README.md`, "OQ hazard" section). Until then, treat the numbers below as
> placeholders.

Sibling of [the coulomb rupture-set benchmark](ec2-sizing-coulomb-rupture-set.md) (#343) and [the crustal
inversion benchmark](ec2-sizing-crustal-inversion.md) (#323), for the OpenQuake **hazard** task
(`runzi hazard oq_hazard`). Like the coulomb builder, hazard runs **to completion**, so the metric is
**wall-clock time**, and the question is *how fast / how cheaply does a hazard job finish, and where do
extra cores stop paying?*

**Concurrency — the EC2 gotcha (#344).** OpenQuake sizes its processpool to the cores it *detects*. On
Fargate (OQ's default) that's exactly the container's vCPU. But on **EC2** — where this benchmark runs —
AWS Batch limits CPU with shares, not cpuset pinning, so the container sees the **host's** cores; the first
matrix run had every cell report `Using 64 processpool workers` and OOM-kill (`oq engine --run` exited
`-9`) the memory-capped container. So OQ must be told its core budget explicitly, exactly like coulomb's
`setNumThreads`: each cell ships `java_threads = vcpu`, and `execute_openquake` writes it to the
`openquake.cfg` `[distribution] num_cores` that `oq` reads (`_cap_oq_num_cores`). With that, `num_cores`
*is* the vCPU axis; the matrix stays family × vCPU.

## Method

- **Workload:** `scripts/ec2_sizing/oq_hazard.template.json` — the **full 2022 GMCM logic tree** (from
  `NSHM_v1.0.4`) × a **single SRM branch** (`srm_single_branch_TEST.json`, co-located so it resolves) ⇒
  one Batch job of **21 gsims**. Sites are the NZ 0.2° grid (`NZ_0_2_NB_1_1`, ~1057), `vs30` 400, 10 IMTs ×
  44 IMTLs. A 4-vCPU pilot at the original ~250 sites (`SRWG214`+`NZ`) ran ~1521 s; the site count was
  raised ~4× so that fixed **serial** overhead (OQ startup, source-model build, export/store) stays a small
  fraction of wall time in the **high-vCPU** cells and doesn't flatten the scaling curve — sites are the
  cleanest parallel axis in classical PSHA (each is independent). ~1057 sites lands well under the 240-min
  job limit; it's still far short of the full 2022 model's ~24 h 3,741-site (`NZ_0_1`) full-LT grid. Tune
  from a `--limit 1` pilot if the job is too short/long or a low-memory (c-family) cell OOMs.
- **Matrix:** instance family {`c6a`, `m6a`} × vCPU {4, 8, 16, 32} × 2 replicates = 16 jobs. Families are
  **pinned** via per-family Batch queues (`terraform/ec2-sizing-benchmark/`), so the vCPU cost curve isn't
  polluted by Batch's allocation strategy picking different families per cell. Memory is sized to ~fill each
  family's per-vCPU RAM (c ≈ 1.8, m ≈ 3.8 GB/vCPU), so a **c-family OOM is the finding** that hazard needs
  more than 2 GB/vCPU. Add `--families r6a` (7.6 GB/vCPU) if the c/m cells OOM, or `--vcpus 64` if the curve
  is still falling at 32.
- **Cost** is analytical fair-share, `(instance $/hr ÷ instance vCPU) × job vCPU × wall-hours` — the cost a
  job would carry on a fully-packed production instance. Because $/hr scales linearly with size, the
  per-vCPU rate is constant within a family, so the cost is exact regardless of the size Batch launched.
- **Validity check.** The collector reads each job's CloudWatch log for OpenQuake's `Using N processpool
  workers` line (`oq_cores`) and flags any cell where it ≠ vCPU — i.e. where the `num_cores` cap silently
  didn't take and the wall time is meaningless. Confirm the summary shows no `!` before trusting a curve.
- Tooling: `scripts/ec2_sizing/submit_oq_hazard_matrix.py` + `collect_oq_hazard_results.py` (see the
  `scripts/ec2_sizing/README.md` OQ-hazard section to reproduce).

## Results

_(placeholder — fill from `collect_oq_hazard_results.py` output; mean of 2 replicates per cell)_

| family | vCPU | instance      | mean wall | mean $/job |
|--------|-----:|---------------|----------:|-----------:|
| c6a    |    4 | c6a.xlarge    |         — |          — |
| c6a    |    8 | c6a.2xlarge   |         — |          — |
| c6a    |   16 | c6a.4xlarge   |         — |          — |
| c6a    |   32 | c6a.8xlarge   |         — |          — |
| m6a    |    4 | m6a.xlarge    |         — |          — |
| m6a    |    8 | m6a.2xlarge   |         — |          — |
| m6a    |   16 | m6a.4xlarge   |         — |          — |
| m6a    |   32 | m6a.8xlarge   |         — |          — |

## Findings

_(to be written from the results — mirror the coulomb doc's structure: memory floor / OOM, parallel-scaling
knee, family comparison.)_

## Recommendation

_(to be written — the goal→pick→$/job→wall table, then the chosen default.)_

## Applied

_(follow-up PR — re-size `default_submission_args` in `runzi/tasks/oq_hazard/oq_hazard_task.py` from the
current 8 vCPU / 32 GiB / 30 min Fargate defaults, and update ADR-0011. Not part of the tooling PR.)_

## Out of scope

- **Disaggregation.** Expected to be larger and more memory-hungry (a different CPU/memory optimum), and it
  additionally needs a stored hazard curve to derive its IML — a separate follow-up reusing this tooling
  parameterised for `OQDisaggArgs`/`OQDisaggJobRunner`.
- **EC2-vs-Fargate.** This benchmark measures EC2 family/vCPU only. Whether hazard should move off its
  current Fargate default onto EC2 needs a Fargate baseline (as the inversion ADR-0011 left that claim
  deferred); not answered here.
