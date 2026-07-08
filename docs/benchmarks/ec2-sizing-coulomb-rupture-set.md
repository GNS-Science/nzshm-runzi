# EC2 job-sizing benchmark — coulomb rupture-set builder

Sibling of [the crustal-inversion benchmark](ec2-sizing-crustal-inversion.md) (#323), for the coulomb
rupture-set builder (`runzi rupset coulomb`). The builder runs **to completion** (unlike the time-bounded
inversion), so the metric is **wall-clock time**, and the question is *how fast / how cheaply does a build
finish, and where do extra cores stop paying?*

## Method

- **Workload:** `INPUT_FILES/coulomb_rupture_sets_1_TEST.json` (fault model `CFM_1_0A_DOM_SANSTVZ`,
  `max_sections` 2000). Template: `scripts/ec2_sizing/coulomb_rupture_set.template.json`.
- **Matrix:** instance family {`c6a`, `m6a`} × vCPU {4, 8, 16, 32, 64} × 2 replicates = 20 jobs. Families
  are **pinned** via per-family Batch queues (`terraform/ec2-sizing-benchmark/`), so the vCPU cost curve
  isn't polluted by Batch's allocation strategy picking different families per cell. **`java_threads` is pinned to
  `ecs_vcpu`** per cell (the builder calls `setNumThreads(java_threads)`), so each cell uses every core it
  pays for and the wall-time-vs-cores curve is meaningful. Memory was sized to ~fill each family's per-vCPU
  RAM (c ≈ 1.8, m ≈ 3.8 GB/vCPU).
- **Cost** is analytical fair-share, `(instance $/hr ÷ instance vCPU) × job vCPU × wall-hours` — the cost
  a job would carry on a fully-packed production instance. Because $/hr scales linearly with size, the
  per-vCPU rate is constant within a family (every c6a size = $0.03825/vCPU-hr, every m6a = $0.0432), so
  the cost is exact regardless of the size Batch actually launched.
- Tooling: `scripts/ec2_sizing/submit_coulomb_matrix.py` + `collect_coulomb_results.py` (see the
  `scripts/ec2_sizing/README.md` coulomb section to reproduce).

## Results

Mean of 2 replicates per cell:

| family | vCPU | instance      | mean wall | mean $/build |
|--------|-----:|---------------|----------:|-------------:|
| c6a    |    4 | c6a.xlarge    |   3_740 s |      $0.1590 |
| c6a    |    8 | c6a.2xlarge   |   2_753 s |      $0.2340 |
| c6a    |   16 | c6a.4xlarge   |   1_956 s |      $0.3325 |
| c6a    |   32 | c6a.8xlarge   |   1_241 s |      $0.4221 |
| c6a    |   64 | c6a.16xlarge  |     939 s |      $0.6384 |
| m6a    |    4 | m6a.xlarge    |   3_859 s |      $0.1852 |
| m6a    |    8 | m6a.2xlarge   |   2_723 s |      $0.2614 |
| m6a    |   16 | m6a.4xlarge   |   2_153 s |      $0.4133 |
| m6a    |   32 | m6a.8xlarge   |   1_326 s |      $0.5091 |
| m6a    |   64 | m6a.16xlarge  |     786 s |      $0.6034 |

## Findings

**1. Compute-bound and low-memory — as suspected.** c6a and m6a post near-identical wall times at every
size, and **no cell OOM'd** even at c-family's ~1.8 GB/vCPU. The build does not need the memory the old
default handed it (30 GB at 4 vCPU = 7.5 GB/vCPU), which on the shared `"optimal"` CE would have steered
it onto expensive memory-optimized **r-family** (the same trap #323 found).

**2. Parallelizes sub-linearly — the knee is at 32 vCPU.** Speedup vs 4 vCPU (c6a): 8→1.36×, 16→1.91×,
32→3.01×, 64→3.98× (16× the cores for ~4× the speed). The marginal cost of buying speed, per doubling:

| step (c6a) | time saved | extra $ | $ per minute saved |
|------------|-----------:|--------:|-------------------:|
| 4 → 8      |   16.5 min |  +0.075 |             0.0045 |
| 8 → 16     |   13.3 min |  +0.099 |             0.0074 |
| 16 → 32    |   11.9 min |  +0.090 |             0.0076 |
| **32 → 64**|  **5.0 min**| **+0.216** |         **0.043** |

Up to 32 vCPU, speed costs ~½–¾ ¢ per minute saved; the 32→64 step costs **~6× more per minute** for the
least time back. Cost per build rises monotonically with cores (sub-linear speedup × constant per-vCPU
price), so the cheapest build is always the smallest.

**3. Family: c6a wins ≤ 32 vCPU; m6a overtakes at 64.** c6a is cheaper at every size up to 32 (compute-
bound → cheaper AMD compute). At 64 vCPU m6a is both faster (786 s vs 939 s) and cheaper ($0.603 vs
$0.638): c6a's scaling stalls with 64 contending threads while m6a still gains — but this only matters
inside the already-diseconomic zone.

## Recommendation

| goal | pick | $/build | wall |
|------|------|--------:|-----:|
| **cheapest** | c6a · 4 vCPU | $0.159 | 62 min |
| balanced (the knee) | c6a · 32 vCPU | $0.422 | 21 min |
| fastest | m6a · 64 vCPU | $0.603 | 13 min |

**c6a is the family** (compute-optimized, cheapest at any sane size). For the default we optimise for
cheapest $/build: **4 vCPU**. Push to 32 vCPU when a human is waiting; never 64.

## Applied

The coulomb and subduction builder `default_submission_args` were re-sized accordingly
(`runzi/tasks/coulomb_rupture_sets/coulomb_rupture_set_builder_task.py`,
`runzi/tasks/subduction_rupture_sets/subduction_rupture_set_builder_task.py`):

| field | old | new | why |
|-------|----:|----:|-----|
| `ecs_vcpu` | 4 | 4 | cheapest $/build (unchanged) |
| `java_threads` | 16 | 4 | track vCPU; 16-on-4 oversubscribed |
| `ecs_memory` (MiB) | 30720 | 7000 | fits under the 8 GiB compute-optimized `c*.xlarge` ceiling (with ECS agent/OS headroom) so `BEST_FIT_PROGRESSIVE` places the job on cheap c-family, not the 16 GiB general-purpose `m*.xlarge`; heap ≈ 5 GB is ample |
| `ecs_max_job_time_min` | 60 | 90 | the 4-vCPU build takes ~62 min — the old limit killed it |
| `ecs_job_definition` | `runzi-fargate-JD` (default) | `runzi-ec2-JD` | these Java builds always run on the EC2 CE; 7000 MiB / 4 vCPU is below Fargate's 8192 MiB floor anyway, so the Fargate default would have failed validation |

The CE pool is `["c6a", "m6a", "c6i", "m6i"]` (ADR-0011, r-family excluded); at 2 GB/vCPU a c-instance is
8 GiB, so requesting the *full* 8192 MiB would overflow the ECS-reserved headroom and force the job onto a
16 GiB m-instance — hence 7000. Subduction is assumed equivalent to coulomb (not independently
benchmarked). Larger fault models or higher `max_sections` may shift the absolute times; re-run the matrix
if the workload changes materially.

## Out of scope

Pinning Graviton (arm64) or Spot capacity for these builds is a deployer/terraform change on the shared
CE — a follow-up only if the code-side default proves insufficient. (The CE is already off `"optimal"` and
excludes r-family, per ADR-0011, so that steering is done.) The per-family instance *pinning* in this
benchmark was throwaway, only to keep the family axis clean — not a production CE change.
