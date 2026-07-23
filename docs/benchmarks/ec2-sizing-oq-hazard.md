# EC2 job-sizing benchmark — OpenQuake hazard

> **Status: matrix run complete (2026-07-23), defaults not yet applied.** Results/findings below are from a
> 20-job run (10 cells × 2 replicates, 4–64 vCPU) on the pinned per-family EC2 queues. Applying the recommendation to
> `default_submission_args` is a considered follow-up (see *Applied*).

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
- **Matrix:** instance family {`c6a`, `m6a`} × vCPU {4, 8, 16, 32} × 2 replicates = 16 jobs, plus a follow-up
  {`c6a`, `m6a`} × 64 vCPU × 2 = 4 jobs (`--vcpus 64`) to confirm the knee. Families are
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

Mean of 2 replicates per cell, over two runs (4–32 vCPU, then 64 via `--vcpus 64`). Every cell passed the
worker-count check (`oq_cores == vcpu`) — the `num_cores` cap took on all 20 jobs, and none OOM'd. Cost is
the fair-share per-vCPU rate, so it is exact even though Batch packed jobs onto larger shared instances
(`instance` below is the exact-fit size the fair-share cost corresponds to; see the co-tenancy note under
Findings).

| family | vCPU | instance      | mean wall | mean $/job |
|--------|-----:|---------------|----------:|-----------:|
| c6a    |    4 | c6a.xlarge    |   4_081 s |    $0.1735 |
| c6a    |    8 | c6a.2xlarge   |   2_496 s |    $0.2121 |
| c6a    |   16 | c6a.4xlarge   |   1_781 s |    $0.3028 |
| c6a    |   32 | c6a.8xlarge   |   1_083 s |    $0.3683 |
| c6a    |   64 | c6a.16xlarge  |     761 s |    $0.5175 |
| m6a    |    4 | m6a.xlarge    |   4_309 s |    $0.2069 |
| m6a    |    8 | m6a.2xlarge   |   2_549 s |    $0.2447 |
| m6a    |   16 | m6a.4xlarge   |   1_599 s |    $0.3070 |
| m6a    |   32 | m6a.8xlarge   |   1_003 s |    $0.3851 |
| m6a    |   64 | m6a.16xlarge  |     751 s |    $0.5771 |

## Findings

**1. Compute-bound and low-memory.** No cell OOM'd — including c-family at ~1.8 GB/vCPU (a 4-vCPU c6a job
ran the full 1057-site, 21-gsim calc in ~7 GB). Hazard does not need the 32 GiB the current default hands
it; the memory dimension the issue worried about is a non-issue for a single SRM branch at this site count.
(The `num_cores` cap is what makes this true on EC2 — uncapped, OQ sized its pool to the host's cores and
OOM'd every cell; see the Concurrency section above and #344.)

**2. Scales sub-linearly; the knee is at 32 vCPU.** Speedup vs 4 vCPU (c6a): 8→1.64×, 16→2.29×, 32→3.77×,
64→5.36× (16× the cores for ~5.4× the speed). Marginal cost of buying speed, per step:

| step (c6a) | time saved | extra $ | $ per minute saved |
|------------|-----------:|--------:|-------------------:|
| 4 → 8      |   26.4 min |  +0.039 |             0.0015 |
| 8 → 16     |   11.9 min |  +0.091 |             0.0076 |
| 16 → 32    |   11.6 min |  +0.066 |             0.0056 |
| **32 → 64**|  **5.4 min**| **+0.149** |         **0.0278** |

The first doubling (4→8) nearly halves wall time for almost nothing (~0.15 ¢/min); speed stays cheap
(~½–¾ ¢/min saved) up to 32. Then **32→64 is the cliff — ~5× worse value per minute** (2.8 ¢) for the least
time back, the same diseconomic wall the coulomb builder hit at 64. So the knee is at **32 vCPU**; 64 buys a
little more speed at a poor rate. Cost per job rises monotonically with cores (sub-linear speedup × constant
per-vCPU price), so the cheapest job is always the smallest.

**3. Family: c6a cheapest everywhere; m6a faster at the top.** c6a is cheaper at every size (compute-bound →
cheaper AMD compute wins). m6a edges ahead on *speed* at ≥16 vCPU (1599 vs 1781 s at 16; 1003 vs 1083 s at
32; 751 vs 761 s at 64) — more memory bandwidth helping once many cores contend — but only inside the
pay-more-for-latency zone.

**Co-tenancy note.** The pinned CE (`instance_types = ["c6a"]`, `BEST_FIT_PROGRESSIVE`, `max_vcpus = 64+`)
packed jobs onto larger shared boxes rather than launching exact-fit instances — the c6a 4/8/16 cells onto
one `c6a.16xlarge`, and the two 64-vCPU replicates onto a 128-vCPU `c6a.32xlarge` (exactly filling it, so no
oversubscription). Fair-share cost is size-independent within a family, so **cost is unaffected**; the
`num_cores` cap kept each job to its own vCPU. Wall times are treated as good here; a fully rigorous run
would pin one job per instance (per-size CEs, or serial submission) to rule out cross-job cache/bandwidth
contention.

## Recommendation

| goal | pick | $/job | wall |
|------|------|------:|-----:|
| **cheapest** | c6a · 4 vCPU | $0.174 | 68 min |
| the one cheap win (halve the time) | c6a · 8 vCPU | $0.212 | 42 min |
| the knee (last economical step) | c6a · 32 vCPU | $0.368 | 18 min |
| fastest (past the knee) | m6a · 64 vCPU | $0.577 | 13 min |

**c6a is the family.** For batch throughput (a real hazard run fans out over many SRM branches → many
jobs, so cheapest-per-job = cheapest total), the default should optimise $/job: **c6a · 4 vCPU**, memory
sized to the ~7 GB the calc used. Take the 4→8 step when latency matters (halves wall time for ~4 ¢); push
toward 32 only when a human is waiting; 64 buys a little more speed at ~5× the cost-per-minute, so skip it.

## Applied

Not yet applied. Two reasons this is a considered follow-up, not an automatic bump of
`default_submission_args` (`runzi/tasks/oq_hazard/oq_hazard_task.py`, currently 8 vCPU / 32 GiB / 30 min):

1. **Target.** These numbers are EC2; hazard's default is **Fargate**. Adopting "c6a · 4 vCPU" means moving
   hazard onto EC2, which still wants the EC2-vs-Fargate baseline ADR-0011 left deferred.
2. **Memory floor.** ~7 GB held for 1 SRM branch × 1057 sites × 10 IMTs; a production run with more sites
   or IMTs needs headroom before trusting a c-family (2 GB/vCPU) size.

## Out of scope

- **Disaggregation.** Expected to be larger and more memory-hungry (a different CPU/memory optimum), and it
  additionally needs a stored hazard curve to derive its IML — a separate follow-up reusing this tooling
  parameterised for `OQDisaggArgs`/`OQDisaggJobRunner`.
- **EC2-vs-Fargate.** This benchmark measures EC2 family/vCPU only. Whether hazard should move off its
  current Fargate default onto EC2 needs a Fargate baseline (as the inversion ADR-0011 left that claim
  deferred); not answered here.
