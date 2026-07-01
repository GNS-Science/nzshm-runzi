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

`SystemArgs.ecs_job_definition` / `ecs_job_queue` (`runzi/arguments.py`) default to these two
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

Fargate is still the default for every task. A job opts into EC2 by setting
`ecs_compute_environment: ec2` in its config file's `sys_arg_overrides`, alongside the EC2 queue
and definition names (constants `EC2_JOB_QUEUE`, `EC2_JOB_DEFINITION` /
`EC2_EXPERIMENTAL_JOB_DEFINITION` in `runzi/arguments.py`):

```json
"sys_arg_overrides": {
  "ecs_compute_environment": "ec2",
  "ecs_job_definition": "runzi-ec2-JD",
  "ecs_job_queue": "runzi-ec2-Q"
}
```

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

To run an experimental image deliberately, override the job definition in a config file's
`sys_arg_overrides`:

```json
"sys_arg_overrides": {
  "ecs_job_definition": "runzi-fargate-experimental-JD"
}
```

runzi resolves whichever job definition you submit to back to a concrete image digest at submit
time and records it (`NZSHM22_RUNZI_ECR_DIGEST`) in toshi provenance, so a run pins exactly which
image it used even though the definition names only a tag.

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
