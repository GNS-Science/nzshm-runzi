# OpenQuake core cap derived from `ecs_vcpu`, not the Java thread arg

## Decision

**Stop overloading one worker arg for two unrelated concepts.** Keep the Java-side thread knob and the
OpenQuake processpool cap as separate fields, each sourced from where its value actually comes from:

- **`java_threads`** (revert the #344 `num_cores` rename) — the per-task **Java** thread count
  (`setNumThreads` / PBS `ppn`). It is a genuine tuning knob, deliberately decoupled from `ecs_vcpu`
  (crustal/subduction inversions set it to 16 on an 8-vCPU box; it's vestigial on AWS but honestly
  Java/PBS-only). No OpenQuake task reads it.
- **OpenQuake processpool cap** — **derived from `ecs_vcpu`**, not independently specified. `build_tasks`
  ships the container's allocated vCPU into `TaskRuntimeArgs` as `allocated_vcpu`; the OQ task feeds it to
  `execute_openquake`, which (only inside AWS Batch) writes it to `openquake.cfg [distribution] num_cores`.
  There is **no independent OQ core knob** — the cap is always exactly the vCPU we requested.

The Batch-only gate (`AWS_BATCH_JOB_ID`) and the `_cap_oq_num_cores` / `openquake.cfg` mechanism from #344
are unchanged; only the **source of the number** changes, from a hand-set `num_cores` to the derived
`ecs_vcpu`.

## Two deciding inputs

1. **The OQ cap is not a free parameter — it *is* the resource request.** OpenQuake auto-detects cores to
   size its processpool. On AWS Batch **EC2** the container sees the *host's* cores (CPU shares, not
   cpuset), so it over-detects and OOM-kills a memory-capped container (#344). The correct cap is exactly
   the vCPU the job requested, which is `ecs_vcpu` — and Batch honors the job-definition vcpus as the
   container's CPU allocation, so `ecs_vcpu` *is* the allocation by construction, with no drift. Sourcing
   the cap from a separate `num_cores` field that merely has to *equal* `ecs_vcpu` builds in a silent sync
   hazard: an override like `submission_arg_overrides: {ecs_vcpu: 16}` leaves OQ capped at the stale
   default 8 (half the cores wasted), and `{ecs_vcpu: 4}` re-opens the OOM. Deriving the cap closes the
   hazard by construction — override `ecs_vcpu` and the cap moves with it.

2. **Java threads and the OQ cap are genuinely different concepts.** `java_threads` is a tuning knob that
   is *intended* to differ from `ecs_vcpu` (the inversion default proves it); the OQ cap is forced to the
   allocation. The #344 rename unified them under `num_cores` on the premise that OQ "also uses it," but
   once OQ derives its cap from `ecs_vcpu` the field is Java/PBS-only again, so `java_threads` is the
   honest name and `num_cores` was churn.

Considered and rejected: **worker self-detection** (the container reads its own vCPU from the ECS
task-metadata endpoint or cgroup `cpu.shares` and caps OQ to that). Runtime discovery earns its keep only
for values that are *unknowable at submit time* — e.g. which physical instance Batch placed you on (the
IMDS instance-type idea in ADR-0011). The vCPU allocation is not such a value: we chose it, it's
`ecs_vcpu`. Self-detection would throw a known value away and reconstruct it from a mechanism that first
has to be *verified* to be populated on Batch-EC2 (Batch uses shares, so a `cpu.max` quota is likely
unset), whose failure mode is the exact OOM we're preventing. It buys no architectural purity we don't
already spend — shipping a value derived from `SubmissionArgs` is the established pattern.

## Consequences / deferred obligations

- **Interaction with [0009](0009-submission-vs-runtime-args.md).** `ecs_vcpu` was submitter-only there
  because "the worker doesn't read it." The OQ worker now legitimately needs it, so `build_tasks` ships a
  derived `allocated_vcpu` into `TaskRuntimeArgs`. This is a scoped, justified addition to the wire
  schema, not a reversal — `ecs_vcpu` itself stays a `SubmissionArgs` field; only its *value* crosses the
  boundary, relabeled as the container's allocation. Populate it **unconditionally** (all task types) so
  `build_tasks` stays task-agnostic; Java workers simply ignore it.
- **Shipped-schema change → image + submitter release together.** `TaskRuntimeArgs` gains `allocated_vcpu`
  and drops `num_cores` (back to `java_threads`), so an old worker image can't parse the new config and
  vice versa — the same release coupling ADR-0009 already imposes.
- **`submission_arg_overrides` key changes back.** Configs that set `num_cores` (only the #344 benchmark
  tooling, uncommitted run artifacts aside) revert to `java_threads`; OQ configs drop it entirely. A stale
  `num_cores` override now fails loud (`setattr` on a model with no such field), not silently — the right
  failure mode for a rename.
- **No downshift knob (YAGNI).** OQ workers always equal `ecs_vcpu`. If a memory-bound run ever wants
  *fewer* OQ workers than vCPU (more RAM per worker), add an optional per-task setting then, clamped to
  `≤ ecs_vcpu` as a model-owned invariant — don't build the clamp before there's a knob to clamp.
- **Land inside #344 (PR #358), before it merges.** This directly revises that PR's `java_threads →
  num_cores` rename and its OQ `num_cores` default; folding it in is cheap now and a churny two-step after
  merge.

## Files (planned)

- `runzi/arguments.py` — `SubmissionArgs`/`TaskRuntimeArgs`: `num_cores` → `java_threads`; add
  `allocated_vcpu` to `TaskRuntimeArgs`.
- `runzi/build_tasks.py` — ship `java_threads=submission_args.java_threads` **and**
  `allocated_vcpu=submission_args.ecs_vcpu`.
- `runzi/tasks/oq_hazard/execute_openquake.py` — cap fed from `allocated_vcpu` (Batch-gate and
  `openquake.cfg` write unchanged).
- `runzi/tasks/oq_hazard/{oq_hazard,oq_disagg}_task.py` — drop `num_cores` from `default_submission_args`;
  pass `allocated_vcpu` to `execute_openquake`.
- The Java task modules + factories (`opensha_task_factory`, coulomb/subduction builders, reports,
  time-dependent, azimuthal) — `num_cores` → `java_threads`.
- `scripts/ec2_sizing/` (submit/collect/README/template) — inject `ecs_vcpu` only; drop the `num_cores`
  override (the cap now derives from it).
- Docs — [0009](0009-submission-vs-runtime-args.md) field table, [0011](0011-ec2-compute-optimized-for-inversions.md)
  OQ note, `CLAUDE.md`, `architecture.md`, benchmark docs.
