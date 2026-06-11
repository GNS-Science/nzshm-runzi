# AWS Batch compute: consolidate to a single Fargate environment

## Decision

**runzi targets a single AWS Batch Fargate compute environment, job definition, and job
queue for every task.** The canonical names are the already-existing Fargate resources:

- Job definition: `Fargate-runzi-opensha-JD`
- Job queue: `BasicFargate_Q`

These are the **defaults** on `SystemArgs` (`runzi/arguments.py`), so task modules no longer
repeat them. A task only sets `ecs_memory` / `ecs_vcpu` / `ecs_max_job_time_min` (and may
override the def/queue if a genuine need ever appears).

The EC2 `BigLever_32GB_8VCPU_v2_JD` / `BigLever_32GB_8VCPU_v2_JQ` path — previously used only by
the OpenQuake hazard and disaggregation tasks — is retired. Those tasks run on Fargate at
8 vCPU / 32 GB.

**Infrastructure-as-code is explicitly deferred.** The compute environment, job definition, and
queue remain hand-created in the AWS console for now. This ADR and `docs/usage/aws_batch.md` are
the interim source of truth and the spec a future IaC module should encode.

## Two deciding inputs

1. **Modern Fargate covers the whole workload.** AWS Fargate now supports up to 16 vCPU /
   120 GB. The OQ tasks were the only reason a separate EC2 ("BigLever") environment existed —
   at 8 vCPU / ~30 GB they fit comfortably inside Fargate's matrix. With that constraint gone,
   there is no task that requires EC2, so a second compute environment is pure maintenance cost.
2. **Everything is hand-managed and duplicated.** Twelve task modules each hard-coded a job
   definition and queue name across two near-identical clusters, and `runzi/aws/aws.py` carried a
   hand-written, duplicate-riddled vcpu/memory assert table. Collapsing to one default removes the
   duplication; one compute environment is far less to maintain by hand until IaC arrives.

## Background

Before this change:

| | OpenSHA / inversion / report tasks (10) | OQ hazard + disagg tasks (2) |
|---|---|---|
| Job definition | `Fargate-runzi-opensha-JD` | `BigLever_32GB_8VCPU_v2_JD` (EC2) |
| Job queue | `BasicFargate_Q` | `BigLever_32GB_8VCPU_v2_JQ` (EC2) |
| Sizing | 4 vCPU / 30720 MB | 8 vCPU / 30000 MB |

`get_ecs_job_config()` sniffed `"Fargate" in job_definition` and, for Fargate, asserted the
vcpu/memory pair against an inline table that only covered up to 4 vCPU and contained duplicate
entries; EC2 jobs were never validated. A note: `ecs_memory=30000` (and `30720`) are **not valid
at 8 vCPU on Fargate** — 8 vCPU memory must be a multiple of 4096 between 16384 and 61440 — so the
OQ migration bumps memory to `32768` (32 GB), and the new validation enforces this for any task.

## Consequences / deferred obligations

Because IaC is deferred, the following are **manual, external obligations** rather than code:

- **No source of truth for the live resources** beyond this ADR + `docs/usage/aws_batch.md`
  until IaC is adopted.
- **Before the OQ tasks are migrated to Fargate** (done in code separately), confirm in the
  console that `Fargate-runzi-opensha-JD` has `platformCapabilities: ["FARGATE"]` and that the
  compute environment behind `BasicFargate_Q` has `maxvCpus` high enough for the desired OQ
  concurrency at 8 vCPU/job. No new resources are required — only capacity/config verification.
- **After the OQ tasks are verified on Fargate**, delete the `BigLever_32GB_8VCPU_v2_*` compute
  environment, job definition, and queue (and any other now-unused envs/defs/queues) so only the
  single Fargate set remains.
- **Static Fargate validation table can drift.** The vcpu/memory matrix is encoded statically in
  `runzi/aws/aws.py`. This is an accepted low-severity trade-off:
  - AWS only ever *expands* the Fargate matrix, so a stale table fails **closed** — it rejects a
    newly-valid combo with a clear error rather than silently accepting an invalid one.
  - `submit_job` is the real validator; the local table is a fast, friendly pre-check, not the
    source of truth.
  - Refresh is cheap: the matrix is a single module-level constant with a doc-comment linking the
    AWS "Fargate task CPU and memory" reference and a `# last verified: YYYY-MM` marker, so a
    future update is a one-line edit.

## Followups not blocking this decision

- **Adopt infrastructure-as-code** (Terraform or AWS CDK) to encode the single compute
  environment, job definition, and queue, replacing the console-managed resources. This ADR plus
  `docs/usage/aws_batch.md` are the spec.
- **Optional dynamic resource validation** — query the Batch/ECS API for the compute
  environment's real capabilities instead of the static matrix. Needs live AWS credentials and is
  heavier; only worth it if the static table proves to drift painfully.
- **Add an EC2 compute environment** only if a future task genuinely exceeds Fargate's limits
  (>16 vCPU / 120 GB, GPU, or fast local scratch).

## Files

- `runzi/arguments.py` — `DEFAULT_JOB_DEFINITION` / `DEFAULT_JOB_QUEUE` constants and the
  `SystemArgs.ecs_job_definition` / `ecs_job_queue` field defaults.
- `runzi/aws/aws.py` — `validate_fargate_resources()` and the Fargate vcpu/memory matrix constant
  consumed by `get_ecs_job_config()`.
- `runzi/tasks/*/*_task.py` — task modules now inherit the default def/queue; OQ tasks carry the
  8 vCPU / 32 GB Fargate sizing.
- `runzi/cli/build_and_deploy_container.py` — deploy default `job_definition` aligned to the
  canonical Fargate name.
- `docs/usage/aws_batch.md` — operator-facing description of the single Fargate architecture.
