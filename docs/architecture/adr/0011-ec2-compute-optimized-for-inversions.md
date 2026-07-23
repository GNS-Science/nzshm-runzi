# EC2 compute target: compute-optimized (AMD-preferred) families for inversions, not `"optimal"`

> **Update (2026-07-09):** the deferred *target* switch (see "Followups" below) has since been made.
> Crustal and subduction inversions now **default to the EC2 job definition** (`runzi-ec2-JD`), not
> Fargate, and their module sizing was refined to **8 vCPU / 14000 MiB** (down from 16384) so the job
> fits compute-optimized `c*.2xlarge` after the ECS agent/OS reservation instead of being bumped to
> general-purpose `m*.2xlarge`. This was prompted by the coulomb rupture-set benchmark
> (`docs/benchmarks/ec2-sizing-coulomb-rupture-set.md`), which confirmed these Java builds are
> compute-bound and cheapest on c-family EC2. The EC2-vs-Fargate throughput baseline named below was
> *not* run; the switch rests on the family/sizing evidence plus EC2's lower per-vCPU price. So the
> "Fargate remains the default" statements below now hold only for the non-inversion tasks.

## Decision

**Replace the EC2 compute environment's `instance_type = ["optimal"]` with a compute-optimized-
preferred, memory-optimized-excluded list — `["c6a", "m6a", "c6i", "m6i"]` — and size crustal
inversions at 8 vCPU.** AMD (`c6a`/`m6a`) and Intel (`c6i`/`m6i`) are both listed; under
`BEST_FIT_PROGRESSIVE` Batch picks the lowest-cost type that fits, so this yields compute-optimized
when the job's memory allows and general-purpose only when it needs the extra RAM — and never the
memory-optimized `r` family. Older generations (`c5`/`m5`) may be appended for capacity if On-Demand
`6*` is short.

Concretely:

- `terraform/batch`: change the `ec2_instance_types` default (and `terraform.tfvars`) from `["optimal"]`
  to the list above. Deployer applies (`terraform/batch`), same posture as ADR-0004/0008.
- **Sizing guidance:** inversion configs request **8 vCPU** (the iterations-per-dollar sweet spot).
  Bumping the crustal/subduction module-default `SubmissionArgs` (currently 4 vCPU) is a small,
  optional follow-up (see below) — not required by this decision.

This changes only the EC2 opt-in target's *instance family selection*. Fargate remains the default for
every task (ADR-0003); this decision does not switch any task from Fargate to EC2.

## Deciding inputs

1. **The benchmark is unambiguous (see `docs/benchmarks/ec2-sizing-crustal-inversion.md`).** At 8 vCPU,
   one job per exact-fit instance: iterations-per-dollar ranks `c6a > m6a > c6i > m6i > r6a > r6i`.
   Two effects, both largely price-independent: AMD `6a` does **~12% more iterations** than Intel `6i`,
   and throughput is **~identical across c/m/r within a vendor** — the inversion is not
   memory-bandwidth-bound, so the family difference is essentially price per vCPU and compute-optimized
   wins. Final energy (solution quality) is flat across every family, so this is pure cost saving.
   `"optimal"` had been landing inversions on **`r6i` — the worst family, ~65% more $/inversion than
   `c6a`.**
2. **Exclude `r`, keep `m` — a memory-floor safety, not a throughput call.** Compute-optimized
   `*.2xlarge` is 16 GiB (~12–14 GB heap); the benchmark rupture set converged there, but a larger
   rupture set needs more heap. Listing the general-purpose `m` family (32 GiB at 8 vCPU) lets such jobs
   still schedule at lowest cost instead of sticking in `RUNNABLE`, while `BEST_FIT_PROGRESSIVE` still
   prefers the cheaper `c` family whenever memory permits. `r` is excluded because it never won on any
   axis.
3. **8 vCPU is the sizing knee.** The inversion runs a fixed 16-thread anneal
   (`selector_threads × averaging_threads`); 4→8 vCPU roughly triples iterations for 2× cost, 8→16
   adds only ~1.2× for 2× cost. Energy is near-identical from 4 vCPU up, so 8 vCPU maximizes
   iterations-per-dollar and quality is not the constraint.

## Background

`#323` benchmarked crustal inversions on the single EC2 compute environment from ADR-0008. Phase 1 (job
sizing on the shared `"optimal"` CE) established the 8-vCPU knee but couldn't compare instance families,
because `BEST_FIT_PROGRESSIVE` collapses a mixed queue onto one type (it chose `r6i`). Phase 2 stood up
one throwaway pinned CE per instance type (`terraform/ec2-sizing-benchmark/`) so each family ran on its
own exact-fit `.2xlarge` — one job per instance, removing the co-tenancy confound — and produced the
ranking above. `"optimal"` resolves to current-gen families (it picked `r6i`/`m6i`), not the legacy
`C4/M4/R4`.

## Consequences / deferred obligations

- **Deployer apply required.** The `ec2_instance_types` change ships as Terraform code in
  `terraform/batch`; a deployer applies it (the federated `runzi-admin` session can't apply it itself).
- **Shared CE.** The EC2 CE is shared by every job that targets EC2. At authoring time only inversions did;
  as of #344 OQ hazard **and** disagg also default to EC2 (see the OQ followup below), so the `c`/`m`
  instance list must accommodate their memory too (hazard requests 30720 MiB → `m6a.2xlarge`).
- **No Fargate baseline.** The benchmark compared EC2 families only; it did **not** measure EC2 vs
  Fargate throughput. This decision therefore does not claim EC2 is cheaper than Fargate, nor switch
  the Fargate default — only which EC2 family is used when EC2 is chosen.
- **AMD prices are estimates.** The `INSTANCE_SPECS` AMD entries are ~10%-below-Intel estimates; the
  ~12% AMD *throughput* edge is measured and independent of price, but refresh the AMD prices before
  quoting absolute AMD dollar savings.
- **Instance-type provenance is time-limited.** With `min_vcpus = 0` the CE terminates instances after
  jobs finish and ECS deregisters them, so `describe_container_instances` returns `MISSING` — cost
  analysis must read the instance type while instances live, or (for pinned runs) pass the known type
  to `collect_results.py --instance-type`.

## Followups not blocking this decision

- **EC2 vs Fargate baseline** — ~~benchmark Fargate at 8 vCPU against `c6a` EC2 to decide whether
  inversions' default *target* (currently Fargate) should change.~~ **Resolved 2026-07-09 (see Update
  at top):** the target was switched to EC2 without a Fargate baseline, on the strength of the
  rupture-set benchmark and EC2's lower per-vCPU price; sizing refined to 8 vCPU / 14000 MiB to fit
  compute-optimized `c*.2xlarge`. A dedicated EC2-vs-Fargate throughput comparison is still worth doing
  if the cost of inversions ever comes under scrutiny.
- **Durable instance-type capture** — have the container read its instance type from IMDS and log it to
  `java_app.<port>.log`, so provenance survives scale-down (parsed from Toshi like iterations/energy)
  and cost no longer needs the ECS/EC2 lookup or its IAM.
- **OQ hazard sizing (#344)** — the same benchmark method is now wired for OpenQuake hazard
  (`scripts/ec2_sizing/submit_oq_hazard_matrix.py` + `collect_oq_hazard_results.py`,
  `docs/benchmarks/ec2-sizing-oq-hazard.md`), matrix = family × vCPU. **Run complete (2026-07-23),
  recommendation applied:** hazard `default_submission_args` moved to **EC2 (`runzi-ec2-JD`), 8 vCPU /
  30720 MiB / 240 min**. Findings: compute-bound; the 4→8 step is the cheapest speedup and the knee is at
  32; c6a is cheapest but production 0.1° grids (~4000 sites) need m-family memory (hence 30720). Like the
  inversion move above, the Fargate→EC2 switch rests on cost + the num_cores fix **without an EC2-vs-Fargate
  baseline** (still deferred). Disagg gets the same defaults as a starting point (not yet independently
  benchmarked — expected more memory-hungry, so re-sizing may follow).
  - **OQ core-detection fix (shipped with the tooling).** The first matrix run exposed a real
    **production** bug for *any* OpenQuake job on EC2: Batch limits CPU with shares, not cpuset, so the
    container sees the **host's** cores; OQ sized its processpool to the whole instance and OOM-killed the
    memory-capped container (`oq engine --run` → `-9`). Fix: `execute_openquake` now caps OQ's
    `openquake.cfg` `[distribution] num_cores` to a shipped core budget (`_cap_oq_num_cores`), fed from the
    `java_threads` runtime arg; `oq_hazard_task` / `oq_disagg_task` default `java_threads=8` (=vCPU). No-op
    on Fargate (the microVM already exposes exactly the requested vCPU); required on EC2.
- **Per-workload targets / Spot** — if OQ ever needs EC2 with a different profile, give it its own
  target rather than widening this list; Spot remains a separate cost lever (ADR-0008).
- **Refresh `INSTANCE_SPECS` prices** (`# last verified:` marker) before publishing absolute costs.

## Files

- `terraform/batch/variables.tf`, `terraform/batch/terraform.tfvars(.example)` — `ec2_instance_types`
  default from `["optimal"]` to `["c6a", "m6a", "c6i", "m6i"]`.
- `docs/benchmarks/ec2-sizing-crustal-inversion.md` — the benchmark method, data, and recommendation
  this ADR adopts.
- `scripts/ec2_sizing/`, `terraform/ec2-sizing-benchmark/` — the benchmark tooling (`#323`).
- (Optional follow-up) `runzi/tasks/inversion/*_solution_task.py` — module-default `ecs_vcpu` 4 → 8.
- [0003](0003-aws-batch-compute-consolidation.md) (Fargate default, unchanged),
  [0008](0008-aws-batch-ec2-compute-environment.md) (the EC2 CE this retunes; `"optimal"` was its
  deliberate starting point, now settled by `#323`).
