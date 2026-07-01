# Split SystemArgs into SubmissionArgs (submitter) and TaskRuntimeArgs (worker)

## Decision

**Split the single `SystemArgs` model into two: `SubmissionArgs` (config the local submitter uses to
shape and submit the Batch job) and `TaskRuntimeArgs` (per-task context the container worker needs).**
Only `TaskRuntimeArgs` is serialized and shipped to the worker (under the config key
`task_runtime_args`); `SubmissionArgs` never crosses the submitter→worker boundary.

Field partition (by where each field is actually read):

| `TaskRuntimeArgs` (shipped → worker) | `SubmissionArgs` (submitter-only) |
|---|---|
| `general_task_id`, `task_count`, `use_api`, `java_gateway_port`, `java_threads` | `task_language`, `jvm_heap_max`, `ecs_max_job_time_min`, `ecs_memory`, `ecs_vcpu`, `ecs_job_definition`, `ecs_job_queue`, `ecs_compute_environment`, `ecs_extra_env` (+ the `resolved_*` derivation) |

`java_threads` is declared per Java task module on `SubmissionArgs` and copied into `TaskRuntimeArgs`
by `build_tasks` (it's the one worker-read field that originates from a module's default config).

## Two deciding inputs

1. **The worker was re-validating fields it never uses.** Each task module's `__main__` rebuilt the
   *entire* `SystemArgs` from the shipped config, but reads only the five runtime fields. So a change
   to a submission-only field broke the worker: making `ecs_job_queue` / `ecs_compute_environment`
   Optional (ADR-0008 derivation) shipped `null`s that an older worker image's required-field model
   rejected with `ValidationError`, crashing every job — even though the worker ignores those fields.
   Splitting the model removes submission fields from the worker's validation surface entirely, so
   that class of submitter↔worker schema-skew bug can't recur for them.

2. **It shrinks the wire schema and deletes a workaround.** `TaskRuntimeArgs` is a small, stable set
   — the only thing that has to evolve compatibly with deployed images. It also lets us delete
   `freeze_batch_target()` (added in #330 solely to keep the derived queue/compute-env serializable
   for the worker); with submission fields no longer shipped, there is nothing to freeze.

## Consequences / deferred obligations

- **The shipped config schema changed** (`config['task_system_args']` → `config['task_runtime_args']`,
  now a trimmed dict). The **worker image and the submitter must be released together** — an old
  image can't parse the new (trimmed) config, and a new image can't parse an old one. This lands
  with #330, whose cutover rebuilds/promotes the image anyway; deploy the image built from this
  branch before submitting with the new code.
- **The config override key is renamed `sys_arg_overrides` → `submission_arg_overrides`** for
  consistency: it overrides `SubmissionArgs` fields. This is a **breaking config-schema change** (a
  clean break — the old key errors with a migration message, no alias). Overriding a runtime field
  (e.g. `use_api`) was already meaningless (`use_api` is forced from `local_config.USE_API` at submit
  time) and now has no field to bind to; runtime context is assembled in `build_tasks`.
- `ComputeEnvironment | None` on `SubmissionArgs.ecs_compute_environment` reverts the `| str` union
  hack (ADR-0008's serialization workaround) — the raw-string setattr path from
  `submission_arg_overrides` is still tolerated by `resolved_compute_environment` and
  `get_ecs_job_config`.

## Files

- `runzi/arguments.py` — `SystemArgs` split into `SubmissionArgs` (keeps `resolved_*`;
  `freeze_batch_target` deleted) and new `TaskRuntimeArgs`.
- `runzi/protocols.py` — `ModuleWithDefaultSysArgs` → `ModuleWithDefaultSubmissionArgs`
  (`default_submission_args: SubmissionArgs`).
- `runzi/automation/task_config.py` — ships `task_runtime_args` (was `task_system_args`).
- `runzi/aws/aws.py`, `runzi/build_tasks.py`, `runzi/job_runner.py`,
  `runzi/automation/{opensha,python}_task_factory.py` — thread `TaskRuntimeArgs`/`SubmissionArgs`;
  `set_system_args` → `set_submission_args`; `build_tasks` assembles `TaskRuntimeArgs` per task.
- The 12 task modules — `default_submission_args = SubmissionArgs(...)` (no `use_api`); worker
  `__main__` rebuilds `TaskRuntimeArgs(**config['task_runtime_args'])`; task classes and
  `inversion_solution_builder.py` take a `TaskRuntimeArgs`.
- [0008](0008-aws-batch-ec2-compute-environment.md) — its `freeze_batch_target` / `| str` union
  serialization workaround is removed here.
