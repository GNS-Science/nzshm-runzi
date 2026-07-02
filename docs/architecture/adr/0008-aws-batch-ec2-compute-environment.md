# AWS Batch EC2: one On-Demand compute environment + queue + job definitions under Terraform

## Decision

**Complete the "one Fargate + one EC2" Batch consolidation (#322) by standing up a single
On-Demand, MANAGED EC2 compute environment, one EC2 job queue, and two EC2 job definitions under
Terraform (`terraform/batch/`), mirroring the Fargate side.** The legacy/duplicate EC2 environments
(`BigLever_*`, `BigLeverOnDemandEC2`, `ToshiHazardPost_*`) are retired by hand in the console.

Concretely:

- **Two Terraform-managed EC2 job definitions**, tracking the *same* floating image tags as their
  Fargate counterparts (no EC2-specific image; `docker-build` moves `:experimental`, `promote`
  moves `:prod`):
  - `runzi-ec2-JD` (prod) → `<ecr>/nzshm22/runzi:prod`
  - `runzi-ec2-experimental-JD` → `<ecr>/nzshm22/runzi:experimental`

  Both carry `platform_capabilities = ["EC2"]`. Their `container_properties` are the Fargate base
  shape **minus** the two Fargate-only fields (`fargatePlatformConfiguration` and
  `networkConfiguration`/`assignPublicIp`); execution role, job role, resting vCPU/memory, env, and
  command mirror the Fargate definitions.

- **One MANAGED EC2 compute environment** (`runzi-ec2-CE`) and **one queue** (`runzi-ec2-Q`).
  On-Demand purchasing; `allocation_strategy = BEST_FIT_PROGRESSIVE`; `min_vcpus = 0` (scales to
  zero when idle, no standing cost); `instance_type = ["optimal"]` (Batch picks from the C/M/R
  families). Subnets/security groups are shared with the Fargate settings. The Batch
  service-linked role is used unless a custom role is supplied.

- **Canonical EC2 name constants** are added to `runzi/arguments.py`
  (`EC2_JOB_DEFINITION`, `EC2_EXPERIMENTAL_JOB_DEFINITION`, `EC2_JOB_QUEUE`). Fargate stays the
  default for every task; EC2 remains an explicit per-job opt-in via a config file's
  `sys_arg_overrides` (`ecs_compute_environment: ec2`, plus `ecs_job_queue` / `ecs_job_definition`
  set to the EC2 names). No submit-path logic changes — `get_ecs_job_config()` already branches on
  `ComputeEnvironment.EC2` for validation, and `resolve_job_definition_digest()` already resolves
  any job definition's tag → digest for provenance.

## Two deciding inputs

1. **An EC2 compute environment is inert without a job definition that targets it.** ADR-0007
   brought only the *Fargate* job definitions under Terraform and explicitly deferred the EC2
   definition to this consolidation. Standing up an EC2 compute environment + queue without a
   matching `platformCapabilities: EC2` definition would leave a half-built target nothing can
   submit to, so the EC2 JDs are part of the same unit of work — not a follow-up.

2. **On-Demand is the honest minimum for the first consolidated EC2 environment.** Spot is cheaper
   but needs the Spot fleet/service-linked role, a bid allocation strategy, and jobs that tolerate
   interruption/retry — none of which the current workload is set up for. On-Demand matches the
   legacy `BigLeverOnDemandEC2` posture, stands up with no extra IAM, and leaves Spot as a clean
   upgrade path if cost ever demands it. Likewise, instance-type/cost tuning is deliberately left
   at `["optimal"]` here because it is its own investigation (#323); `"optimal"` gives a working,
   self-tuning environment without pre-committing to hardware choices that issue is meant to make.

## Background

ADR-0003 consolidated the workload onto Fargate and retired the old EC2 `BigLever_32GB_8VCPU_v2_*`
path, re-supporting EC2 only as a per-job opt-in — at the time **fully config-driven, with no
canonical EC2 names** (there was no single canonical EC2 target to name). ADR-0004 brought the
Fargate compute environment + queue under Terraform; ADR-0007 brought the two Fargate job
definitions under Terraform via floating tags and flagged the EC2 definition as a followup for
#322. This ADR closes that loop: because #322 creates exactly **one** canonical EC2 compute
environment + queue + definition pair, it now makes sense to name them in code — refining
ADR-0003's addendum ("no canonical EC2 names") now that a canonical EC2 target exists. Fargate
remains the default; this does not reopen the retired BigLever path.

## Consequences / deferred obligations

Terraform *code* for the EC2 resources ships in the runzi repo, but the cutover is ordered and
partly deployer-credentialed (same posture as ADR-0004/0007):

- **Discovery before apply.** The EC2 instance-profile ARN and a sensible `max_vcpus` must be read
  from a live EC2 compute environment (`aws batch describe-compute-environments`) and filled into
  `terraform.tfvars` — the live values can't be read from CI, so `terraform.tfvars.example` carries
  `TODO`s (matching the ADR-0007 convention).
- **Apply, then retire.** A deployer applies the EC2 compute environment → queue → two definitions
  (created fresh; the legacy EC2 environments are **not** imported, since they're slated for
  deletion), smoke-tests a job against `runzi-ec2-Q` / `runzi-ec2-JD`, then retires
  `BigLever_*`, `BigLeverOnDemandEC2`, and `ToshiHazardPost_*` compute envs/queues **by hand in the
  console** (disable → drain → delete). `terraform plan` must be clean afterwards.
- **EC2 sizing has no static matrix.** Unlike Fargate, EC2 vCPU/memory pairs aren't validated
  against a table (`validate_ec2_resources()` is a light positive-value check only). An oversized
  EC2 job sits in `RUNNABLE` indefinitely rather than erroring — the operator-facing failure mode
  documented in `docs/usage/aws_batch.md`.
- **Permissions.** Per ADR-0006/0007 the task-execution/job role lives on the job definition
  (Terraform substrate); the EC2 JDs reuse the same `execution_role_arn` / `job_role_arn` as the
  Fargate JDs, so no new access-tier IAM is required for this change.
- **EC2 needs its own egress-capable subnets (found during smoke test).** EC2 container instances
  must reach the ECS/ECR endpoints to register, so they need a NAT gateway or auto-assigned public
  IPs — unlike Fargate, whose ENIs get a public IP via `assign_public_ip = ENABLED` in the shared
  public/no-NAT subnet. Reusing the Fargate subnet leaves EC2 instances with no egress; they never
  register and jobs stick in `RUNNABLE`. The EC2 CE therefore has its own `ec2_subnets` /
  `ec2_security_group_ids` (falling back to the Fargate values if unset), set to the subnets/SG a
  working EC2 compute environment already uses.

## Followups not blocking this decision

- **Instance-type / cost optimization** — evaluate specific families/sizes and Spot vs On-Demand
  economics. Tracked in **#323**; `["optimal"]` + On-Demand is the deliberate starting point.
- **Spot compute environment** — a future upgrade path (Spot fleet role + interruption-tolerant
  retry) if cost demands it; nothing here blocks adding a second Spot environment behind the queue.
- **Ergonomic EC2/`--experimental` submission flag** — still deferred (ADR-0007); EC2 opt-in uses
  `sys_arg_overrides` until the JD/compute-env set is confirmed stable, which this ADR advances.

## Addendum: queue + compute-environment derive from the job definition

Smoke-testing the EC2 target showed that requiring a user to set `ecs_job_definition`,
`ecs_job_queue`, **and** `ecs_compute_environment` consistently is friction and a foot-gun (an EC2
job definition submitted to the Fargate queue sits in `RUNNABLE` forever). Each canonical job
definition has exactly one correct queue + compute-environment type, so **the user now picks only
the job definition; the queue and compute-environment type derive from it.** A `JOB_DEFINITION_TARGETS`
registry in `runzi/arguments.py` maps each canonical job definition to its `BatchTarget(job_queue,
compute_environment)`; `ecs_job_queue` / `ecs_compute_environment` become `None`-default *override
inputs*, and `SystemArgs.resolved_job_queue` / `resolved_compute_environment` return the explicit
override if set, else the job definition's target. An unknown/custom job definition falls back to
the Fargate target, so behaviour is unchanged unless a config explicitly sets those fields.

The derivation lives on the model as **compute-on-read properties**, not a `model_validator`,
because `sys_arg_overrides` are applied by `setattr` after construction (`runzi/job_runner.py`) and
pydantic doesn't re-run validators on assignment — a stored/validated value would go stale when the
job definition is overridden. A pure read-time resolver is never stale and needs no cooperation from
callers. This refines ADR-0003's addendum further: EC2 is still opt-in, but no longer
"fully config-driven" — the canonical names carry their own routing.

## Files

- `terraform/batch/main.tf` — `aws_batch_compute_environment.ec2`, `aws_batch_job_queue.ec2`,
  `local.ec2_container_properties`, and the `aws_batch_job_definition.ec2_prod` / `.ec2_experimental`
  resources.
- `terraform/batch/variables.tf`, `outputs.tf`, `terraform.tfvars.example` — the EC2 variables
  (instance role, max vCPUs, instance types, allocation strategy, names, resting sizing), the four
  EC2 ARN outputs, and the `TODO`-marked discovery section.
- `runzi/arguments.py` — `EC2_JOB_DEFINITION`, `EC2_EXPERIMENTAL_JOB_DEFINITION`, `EC2_JOB_QUEUE`;
  the `BatchTarget` / `JOB_DEFINITION_TARGETS` registry and `SystemArgs.resolved_job_queue` /
  `resolved_compute_environment` properties (addendum). `runzi/build_tasks.py` reads the resolved
  properties.
- `docs/usage/aws_batch.md` — EC2 target, canonical names, when to use EC2 vs Fargate.
- `terraform/batch/README.md` — EC2 discovery + apply-order + legacy-retirement runbook.
- [0003](0003-aws-batch-compute-consolidation.md) — its addendum's "no canonical EC2 names" point is
  refined here now that a single canonical EC2 target exists. [0007](0007-job-definition-terraform-tag-publish.md)
  — its EC2-job-definition followup is actioned here.
