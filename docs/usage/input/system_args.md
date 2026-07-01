---
hide:
  - toc
---
These arguments have defaults for every job type. They can be overwritten (via `submission_arg_overrides`) as described in the [Introduction](index.md). Not all apply to every job type, e.g. python tasks do not use the `java_*` arguments and locally run tasks do not use the `ecs_*` arguments.

`SubmissionArgs` is the submitter-side config (ECS sizing, job definition, queue/compute env); `TaskRuntimeArgs` is the per-task context shipped to the worker. See ADR-0009.

::: runzi.arguments.SubmissionArgs
    options:
      show_source: false
      inherited_members: true

::: runzi.arguments.TaskRuntimeArgs
    options:
      show_source: false
      inherited_members: true
