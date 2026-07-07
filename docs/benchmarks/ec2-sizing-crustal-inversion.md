# EC2 sizing benchmark — crustal inversion (#323, Phase 1 intermediate results)

**Status:** intermediate. Phase 1 (job sizing on the shared `"optimal"` EC2 CE) is complete; Phase 2
(instance-type pinning) is the follow-up. Prices are approximate (see the caveats) so treat absolute
dollar figures as indicative and rely on *relative* comparisons.

## Method

- **Workload:** one representative crustal inversion (`rupture_set_id RmlsZToxMDAwNjk=`), time-bounded
  at `max_inversion_time = 10 min`, `completion_energy = 0` — every job runs the full wall clock, so
  the output (iterations / perturbations / final energy) is the throughput/quality signal.
- **Anneal threads fixed at 16** (`selector_threads 4 × averaging_threads 4`) across all cells, so
  vCPU below 16 deliberately oversubscribes. Requested vCPU throttles the JVM via
  `-XX:ActiveProcessorCount` + the ECS cgroup CPU limit.
- **Grid:** vCPU {4, 8, 16} × memory:vCPU ratio {2:1 `C`, 4:1 `M`, 8:1 `R`} × 3 replicates, submitted
  to the shared `runzi-ec2-CE` (`BEST_FIT_PROGRESSIVE`, `instance_type = ["optimal"]`).
- **Cost** = fair-share `(instance $/hr ÷ instance vCPU) × job vCPU × wall-hours`, using the instance
  type each job **actually** ran on (read back from Batch→ECS→EC2), us-east-1 On-Demand.
- Tooling: `scripts/ec2_sizing/{submit_matrix,collect_results}.py`.

## Results

**Run 1 — full grid (all ratios).** Batch packed the whole queue onto `r6i.12xlarge`:

| vCPU | ratio | mean_iters | mean_energy | iters/$ | instance |
|---|---|---|---|---|---|
| 8 | R | 364,454,208 | 3,137 | 3,882,520,210 | r6i.12xlarge |
| 4 | R | 174,796,045 | 3,190 | 3,690,760,201 | r6i.12xlarge |
| 8 | M | 325,746,188 | 3,143 | 3,452,081,612 | r6i.12xlarge |
| 4 | C | 160,612,147 | 3,193 | 3,358,160,459 | r6i.12xlarge |
| 4 | M | 150,167,143 | 3,207 | 3,161,530,628 | r6i.12xlarge |
| 16 | R | 564,618,556 | 3,114 | 3,003,924,447 | r6i.12xlarge |
| 8 | C | 272,358,576 | 3,155 | 2,879,754,110 | r6i.12xlarge |
| 16 | M | 463,918,004 | 3,118 | 2,470,019,766 | r6i.12xlarge |
| 16 | C | 450,978,695 | 3,122 | 2,415,711,877 | r6i.12xlarge |

**Run 2 — 8:1 `R` cells dropped (`--ratios C M`).** Queue shifted to `r6i.8xlarge`, with the lowest-
demand cells catching some `m6i`:

| vCPU | ratio | mean_iters | mean_energy | iters/$ | instance |
|---|---|---|---|---|---|
| 8 | C | 439,968,330 | 3,126 | 4,669,026,199 | r6i.8xlarge |
| 4 | C | 160,430,287 | 3,188 | 4,088,279,288 | m6i.2xlarge, r6i.8xlarge |
| 8 | M | 349,974,426 | 3,140 | 3,707,877,536 | r6i.8xlarge |
| 4 | M | 159,537,773 | 3,199 | 3,356,040,941 | r6i.8xlarge |
| 16 | C | 537,663,440 | 3,112 | 3,165,110,274 | m6i.4xlarge, r6i.8xlarge |
| 16 | M | 521,266,714 | 3,114 | 2,765,065,141 | r6i.8xlarge |

## Findings

1. **8 vCPU is the iters/$ sweet spot** — robust across both runs. 4→8 vCPU ~triples iterations for
   2× cost (win); 8→16 adds only ~1.2× for 2× cost (loss).
2. **Solution quality is essentially flat.** Final energy sits at ~3110–3200 across *every* cell — only
   a ~2–3% improvement from 4→16 vCPU despite iterations varying 3×. Within a 10-min budget all these
   sizes converge to about the same solution; extra compute buys iterations, not meaningfully better
   energy. (This is why energy, not just iterations, is tracked — iterations alone oversell big sizes.)
3. **A shared `"optimal"` CE collapses onto one instance type.** `BEST_FIT_PROGRESSIVE` picks a type
   for the whole queue, driven by the most demanding jobs — so the memory-ratio/`C`/`M`/`R` axis is
   moot (all cells ran on r6i). Dropping the 128 GB 8:1 cells only moved r6i.12xlarge → r6i.8xlarge.
   **A real per-family comparison needs instance-type pinning (Phase 2).**
4. **`"optimal"` uses current-gen families** (m6i/c6i/r6i, m5/c5/r5), not the legacy C4/M4/R4.
5. **Everything ran on r6i** (memory-optimized, ~$0.063/vCPU-hr). A compute-optimized `c6i` is
   ~30% cheaper per vCPU and, if the inversion is compute-bound, could improve absolute cost/iteration —
   the open Phase-2 question.

## Recommendation (interim)

- **Size crustal inversions at ~8 vCPU** for best iterations-per-dollar. If solution *quality* is the
  goal rather than raw iterations, even 4 vCPU is adequate (energy is near-identical) and cheaper.
- Defer changing the crustal default `SubmissionArgs` (currently 4 vCPU) until Phase 2 settles the
  family/absolute-cost question; that change would get its own ADR.

## Caveats

- **Prices are approximate** (`INSTANCE_SPECS`, `# last verified: 2026-07`) — refresh before quoting
  absolute dollars; relative cross-cell comparisons are fine.
- **Co-tenancy affects throughput.** The same 8C config did 272M iters packed on a 48-vCPU box (run 1)
  vs 440M on a 32-vCPU box (run 2) — shared memory bandwidth/turbo depress per-job throughput even with
  cgroup CPU limits. Relative vCPU ranking is stable; absolute iters/$ drifts with packing. Phase 2's
  one-job-per-instance pinning removes this confound.

## Next: Phase 2

Compare instance *families* at 8 vCPU by pinning each to its exact-fit `.2xlarge`
(`c6i`/`m6i`/`r6i` + AMD `c6a`/`m6a`/`r6a`) — one job per instance, so no co-tenancy confound and a
clean family + absolute-cost comparison. Rather than re-pinning the shared `runzi-ec2-CE` once per
family, `terraform/ec2-sizing-benchmark/` stands up one throwaway pinned CE + queue **per instance
type in a single `terraform apply`**, and one `terraform destroy` removes them all (the shared CE is
never touched). `submit_matrix.py --job-queue <queue> --vcpus 8 --memory-mb 14000` routes each family's
jobs to its queue; see that module's README for the runbook. Deployer credentials required.
