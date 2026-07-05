This describes the AWS Batch architecture `runzi` submits jobs to in `--cluster-mode AWS`. It is
the operator-facing companion to the decision recorded in
[`docs/architecture/adr/0003-aws-batch-compute-consolidation.md`](../architecture/adr/0003-aws-batch-compute-consolidation.md).

# Single Fargate architecture (default)

Every task module submits to the same compute environment, job definition, and job queue by
default. EC2 is also available as an explicit per-job opt-in — see
["Targeting EC2"](#targeting-ec2) below — but Fargate remains what every task gets unless a job
asks otherwise.

- **Compute environment**: Fargate, backing the queue below. `maxvCpus` must be high enough for
  the desired concurrency at up to 8 vCPU/job (the largest current task size, used by the OQ
  hazard/disagg tasks).
- **Job definition**: `runzi-fargate-JD` (the default/prod definition). A second
  `runzi-fargate-experimental-JD` is identical but tracks the `:experimental` image tag — see
  ["Publishing images & the two job definitions"](#publishing-images--the-two-job-definitions).
  - `platformCapabilities: ["FARGATE"]`
  - Container image: the `nzshm22/runzi` image at a floating tag (`:prod` for the default
    definition, `:experimental` for the experimental one) — not a pinned digest
  - IAM role: the task execution/job role used to pull the image and run the container
  - Job-definition-owned env vars (not forwarded by runzi; see
    [`environment_variables.md`](environment_variables.md#aws-batch-job-definition-env-vars)):
    - `NZSHM22_TOSHI_M2M_SECRET_ARN`
    - `NZSHM22_TOSHI_COGNITO_DOMAIN`
- **Job queue**: `BasicFargate_Q`

`SubmissionArgs.ecs_job_definition` / `ecs_job_queue` (`runzi/arguments.py`) default to these two
names (`DEFAULT_JOB_DEFINITION` / `DEFAULT_JOB_QUEUE`), so task modules only need to set
`ecs_memory` / `ecs_vcpu` / `ecs_max_job_time_min`. `get_ecs_job_config()`
(`runzi/aws/aws.py`) validates every `vcpu`/`memory` pair against AWS's published Fargate
CPU/memory matrix before submission, and raises if a job won't fit.

# Targeting EC2

There is one canonical EC2 target, mirroring Fargate (see
[`docs/architecture/adr/0008-aws-batch-ec2-compute-environment.md`](../architecture/adr/0008-aws-batch-ec2-compute-environment.md)):

- **Compute environment**: `runzi-ec2-CE` — a single On-Demand, MANAGED environment that scales to
  zero when idle and lets Batch pick instance types from the C/M/R families (`instance_type =
  ["optimal"]`; instance-type tuning is tracked in #323).
- **Job definitions**: `runzi-ec2-JD` (prod) and `runzi-ec2-experimental-JD`, `platformCapabilities:
  ["EC2"]`, tracking the *same* `:prod` / `:experimental` image tags as the Fargate definitions.
- **Job queue**: `runzi-ec2-Q`.

Fargate is still the default for every task. A job opts into EC2 by choosing an EC2 job
definition — **that's the only key you need**. The queue and compute-environment type derive from
the job definition (each canonical definition has exactly one correct target), so you can't
accidentally submit an EC2 definition to the Fargate queue:

```json
"submission_arg_overrides": {
  "ecs_job_definition": "runzi-ec2-JD"
}
```

If you ever need a non-standard pairing, `ecs_job_queue` and `ecs_compute_environment` remain
available as explicit overrides and take precedence over the derived values. The derivation is a
registry (`JOB_DEFINITION_TARGETS` in `runzi/arguments.py`) mapping each canonical job definition
to its `(queue, compute-environment)`; an unknown/custom job definition falls back to the Fargate
target.

**Validation is light on purpose.** Unlike Fargate, EC2 has no fixed CPU/memory matrix —
`resourceRequirements` are minimums that the Batch scheduler bin-packs onto whatever instance
types your compute environment offers. `validate_ec2_resources()` (`runzi/aws/aws.py`) only
checks that vCPU is a positive integer and memory is positive; it can't validate against real
instance sizes because runzi doesn't know what's in your compute environment.

**The failure mode to watch for:** if you request more memory than any instance in the compute
environment can actually allocate, the job won't error at submission — it will sit in
`RUNNABLE` forever with no clear message. An instance's *allocatable* memory is somewhat less
than its advertised RAM (the OS, ECS agent, and Docker daemon reserve some), so size EC2 jobs
with margin below your largest instance's total memory, not right up against it.

# Publishing images & the two job definitions

The job definitions track **floating image tags**, not pinned digests, so publishing a new image
never re-registers a job definition (see
[`docs/architecture/adr/0007-job-definition-terraform-tag-publish.md`](../architecture/adr/0007-job-definition-terraform-tag-publish.md)):

- `runzi utils docker-build` builds the image, pushes it to ECR, and moves the `:experimental`
  tag onto it. `runzi-fargate-experimental-JD` tracks `:experimental`, so the new image is live for
  experimental submissions on their next run — without touching the shared prod surface.
- `runzi utils promote` moves the `:prod` tag onto an already-published image. `runzi-fargate-JD`
  (the default) tracks `:prod`, so this — and only this — changes the image default submissions run.
  It is a deliberate, confirmed, CloudTrail-audited step.

To run an experimental image deliberately, override just the job definition in a config file's
`submission_arg_overrides` (the queue and compute-environment type follow the definition automatically):

```json
"submission_arg_overrides": {
  "ecs_job_definition": "runzi-fargate-experimental-JD"
}
```

runzi resolves whichever job definition you submit to back to a concrete image digest at submit
time and records it (`NZSHM22_RUNZI_ECR_DIGEST`) in toshi provenance, so a run pins exactly which
image it used even though the definition names only a tag.

# Inspecting jobs (`runzi batch`)

Federated Cognito users have no AWS console access, so `runzi batch` surfaces the state of the jobs
a submission produced. When you submit in `--cluster-mode AWS`, runzi prints a `GENERAL_TASK_ID`;
pass it to:

```bash
runzi batch status <GENERAL_TASK_ID>
```

This lists every Batch job for that general task (across both the Fargate and EC2 queues) with its
status, run duration, and creation time. It is read-only and needs only the `batch:ListJobs` /
`batch:DescribeJobs` permissions already granted to the `runzi-batch` access tier — log in with
`toshi-auth login` first.

**How it finds the jobs — a naming contract.** AWS Batch `list_jobs` can filter by queue and by a
job-name prefix, but not by tags or the container config. So at submit time runzi encodes a
sanitised `general_task_id` token as the **prefix** of each Batch job name
(`<gt-token>-<base>-<task_count>`; see `runzi/aws/batch_query.py:batch_job_name`), and `status`
queries with a `JOB_NAME` `<gt-token>-*` filter. Any future change to job naming **must preserve
this prefix**, or `runzi batch status` will stop finding jobs.

**Caveats.** AWS Batch retains terminal (SUCCEEDED/FAILED) jobs for only ~24h, so older jobs won't
appear. The name encoding is also forward-only — jobs submitted before this feature shipped are not
discoverable. (Terminate, log-fetching, and config decode are intentionally out of scope for this
read-only version; log-fetching would additionally require a `logs:GetLogEvents` grant.)

Each swept argument (an argument whose value differs across this general task's jobs) is shown as
its own column, decoded from each job's own shipped config. Because the swept columns are inferred
from the jobs still visible in AWS Batch, and Batch retains terminal jobs only ~24h, a swept
argument that happens to be constant across the surviving jobs will not appear as a column.

# Infrastructure-as-code

Both the **Fargate** (compute env, `BasicFargate_Q`, `runzi-fargate-*` definitions) and **EC2**
(`runzi-ec2-CE`, `runzi-ec2-Q`, `runzi-ec2-*` definitions) surfaces are managed by Terraform in
[`terraform/batch/`](../../terraform/batch/) — see that directory's `README.md` for the operator
runbook (discovery, state bucket, import/create, day-to-day `plan`/`apply`),
[`docs/architecture/adr/0004-aws-batch-iac-terraform.md`](../architecture/adr/0004-aws-batch-iac-terraform.md)
(Fargate compute env + queue),
[`docs/architecture/adr/0007-job-definition-terraform-tag-publish.md`](../architecture/adr/0007-job-definition-terraform-tag-publish.md)
(job definitions via floating tags), and
[`docs/architecture/adr/0008-aws-batch-ec2-compute-environment.md`](../architecture/adr/0008-aws-batch-ec2-compute-environment.md)
(EC2 compute env + queue + definitions).

The Terraform owns each definition's **shape** (IAM role, `platformCapabilities`, sizing, M2M env
vars, and which tag it tracks); the **image content** under a tag is published self-serve via
`docker-build` / `promote` above. Changing a definition's shape is a `terraform apply`; changing
the image it runs is a tag move, not a Terraform change.
