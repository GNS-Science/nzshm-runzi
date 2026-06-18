This describes the AWS Batch architecture `runzi` submits jobs to in `--cluster-mode AWS`. It is
the operator-facing companion to the decision recorded in
[`docs/architecture/aws-batch-compute-consolidation.md`](../architecture/aws-batch-compute-consolidation.md).

# Single Fargate architecture

Every task module submits to the same compute environment, job definition, and job queue. There
is no EC2 compute environment.

- **Compute environment**: Fargate, backing the queue below. `maxvCpus` must be high enough for
  the desired concurrency at up to 8 vCPU/job (the largest current task size, used by the OQ
  hazard/disagg tasks).
- **Job definition**: `Fargate-runzi-opensha-JD`
  - `platformCapabilities: ["FARGATE"]`
  - Container image: the `nzshm22/runzi` image built and pushed by
    `runzi utils docker-build` (`runzi/cli/build_and_deploy_container.py`)
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

# Updating the job definition

`runzi utils docker-build` builds the image, pushes it to ECR, and re-registers
`Fargate-runzi-opensha-JD` with the new image (`update_job_definition()` in
`runzi/cli/build_and_deploy_container.py`). It carries forward the existing definition's
`platformCapabilities`, `parameters`, and `containerProperties` (with the image swapped) — AWS
defaults `platformCapabilities` to `EC2` when omitted, which would silently break Fargate's
fractional vCPU values, so this must always be forwarded explicitly.

# Future: infrastructure-as-code

The compute environment, job definition, and job queue above are currently created and managed
by hand in the AWS console — there is no Terraform/CDK/CloudFormation for them. This doc and the
ADR are the interim source of truth.

When IaC is adopted, it should encode:
- The Fargate compute environment (`maxvCpus`, subnets, security groups)
- The `Fargate-runzi-opensha-JD` job definition (image reference, IAM role, `platformCapabilities`,
  the M2M env vars above)
- The `BasicFargate_Q` job queue

Until then, any change to these resources must be made manually in the console and reflected back
into this doc.
