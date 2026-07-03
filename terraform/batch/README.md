# runzi AWS Batch Terraform

Manages the consolidated **one-Fargate-plus-one-EC2** Batch surface that runzi submits jobs to:

- **Fargate** (default for every task): the compute environment, the `BasicFargate_Q` queue, and
  the two job definitions `runzi-fargate-JD` / `runzi-fargate-experimental-JD`.
- **EC2** (explicit per-job opt-in): the `runzi-ec2-CE` compute environment, the `runzi-ec2-Q`
  queue, and the two job definitions `runzi-ec2-JD` / `runzi-ec2-experimental-JD`.

See
[`docs/architecture/adr/0004-aws-batch-iac-terraform.md`](../../docs/architecture/adr/0004-aws-batch-iac-terraform.md)
(Fargate compute env + queue),
[`docs/architecture/adr/0007-job-definition-terraform-tag-publish.md`](../../docs/architecture/adr/0007-job-definition-terraform-tag-publish.md)
(job definitions via floating image tags), and
[`docs/architecture/adr/0008-aws-batch-ec2-compute-environment.md`](../../docs/architecture/adr/0008-aws-batch-ec2-compute-environment.md)
(EC2 compute env + queue + definitions, #322) for the decision records.

The job definitions track floating ECR tags (`:prod` / `:experimental`) rather than pinned
digests, so they are static — they are **not** re-registered on a code deploy. Image content
changes by moving the tag in ECR (`runzi utils docker-build` moves `:experimental`,
`runzi utils promote` moves `:prod`), never by a `terraform apply`.

Run everything in this directory (`terraform/batch/`) — it's a standalone Terraform root.

## Prerequisites

- Terraform >= 1.10 (for native S3 state locking via `use_lockfile`).
- **Deployer-level AWS credentials** — read+write to Batch (for discovery/import/apply) *and*
  read/write to the `nzshm22-runzi-tfstate` state bucket. Run this with the same deployer
  credentials used for `terraform/access/` / `sls deploy`, **not** the federated `runzi-admin`
  session (which no longer holds Terraform-state access — see ADR-0005). Provisioning Batch infra
  is a deployer/devops activity, not a runzi access-tier one.

## One-time: state bucket bootstrap

This root's state lives in S3 (`backend.tf`), but that bucket isn't created by this root — it's
a manual, one-time bootstrap, the same way the Batch resources themselves were hand-created.

Check whether it already exists before creating a new one:

```bash
aws s3 ls | grep tfstate
```

If it doesn't exist, create it once (versioning + public-access-block recommended):

```bash
aws s3api create-bucket --bucket nzshm22-runzi-tfstate --region us-east-1
aws s3api put-bucket-versioning --bucket nzshm22-runzi-tfstate \
  --versioning-configuration Status=Enabled
aws s3api put-public-access-block --bucket nzshm22-runzi-tfstate \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

Update `backend.tf`'s `bucket` value if you used a different name.

## Discovery: find the live resource config

Before writing/importing, capture the **exact** live config so `terraform plan` comes back clean
after import — these become your `terraform.tfvars` values.

```bash
# Find the compute environment backing BasicFargate_Q
aws batch describe-job-queues --job-queues BasicFargate_Q --region us-east-1

# Then describe that compute environment by the name/ARN from the queue's
# computeEnvironmentOrder
aws batch describe-compute-environments --region us-east-1
```

From the output, note:
- Compute environment **name**, `maxvCpus`, `subnets`, `securityGroupIds` → `compute_environment_name`, `max_vcpus`, `subnets`, `security_group_ids`
- Job queue **priority** → `job_queue_priority`

For the job definitions, capture the live `Fargate-runzi-opensha-JD` shape — the new definitions
must behave identically apart from the tagged image. This query surfaces every value you need:

```bash
aws batch describe-job-definitions --job-definition-name Fargate-runzi-opensha-JD \
  --status ACTIVE --region us-east-1 \
  --query 'jobDefinitions[0].containerProperties.{resourceRequirements:resourceRequirements, networkConfiguration:networkConfiguration, executionRoleArn:executionRoleArn, jobRoleArn:jobRoleArn, environment:environment}'
```

Map the `containerProperties` fields to variables:
- `executionRoleArn` → `execution_role_arn`; `jobRoleArn` → `job_role_arn` (or `""` to omit).
- `resourceRequirements` → the `VCPU` entry is `default_vcpu`, the `MEMORY` entry (MiB) is
  `default_memory`. These are **resting defaults** (runzi overrides vCPU/memory per-job via
  `containerOverrides`), but they must still form a **valid Fargate pair** or registration fails —
  see `FARGATE_VCPU_MEMORY_MB` in `runzi/aws/aws.py`.
- `networkConfiguration.assignPublicIp` → `assign_public_ip`. If the output has **no**
  `networkConfiguration` block, set `assign_public_ip = ""` so the new definitions omit it too (AWS
  treats absent as `DISABLED`).
- static `environment` entries → split by toshi stage (ADR-0010): stage-agnostic vars (e.g.
  `NZSHM22_S3_UPLOAD_WORKERS`) go in `job_definition_environment`; the toshi auth pair
  (`NZSHM22_TOSHI_M2M_SECRET_ARN` + `NZSHM22_TOSHI_COGNITO_DOMAIN`) goes in
  `prod_job_definition_environment` (PROD toshi, for the `:prod` JDs) and
  `experimental_job_definition_environment` (TEST toshi, for the `:experimental` JDs). The prod secret
  ARN must also be readable by the external `toshi_batch_ECS_TaskExecution` role (see ADR-0010).
- `image_repository` → the ECR repo URI **without** a tag.

Copy `terraform.tfvars.example` to `terraform.tfvars` and fill these in (gitignored — it's
environment-specific).

### EC2 discovery (ADR-0008, #322)

The EC2 compute environment is **created fresh**, but several values should be **copied from a
working EC2 compute environment** (e.g. `BigLeverOnDemandEC2` / `ToshiHazardPost_*`) so the new one
is sized, permissioned, and — critically — **networked** like a config that already runs jobs:

```bash
aws batch describe-compute-environments --region us-east-1 \
  --query 'computeEnvironments[?computeResources.type==`EC2`].{name:computeEnvironmentName, instanceRole:computeResources.instanceRole, maxvCpus:computeResources.maxvCpus, subnets:computeResources.subnets, sgs:computeResources.securityGroupIds}'
```

Map:
- `instanceRole` → `ec2_instance_role_arn` (the ECS instance-profile ARN the container instances run under).
- `maxvCpus` (or the desired concurrency) → `ec2_max_vcpus`.
- `subnets` → `ec2_subnets` and `securityGroupIds` → `ec2_security_group_ids`. **Do NOT reuse the
  Fargate `subnets` / `security_group_ids`.** The Fargate subnet is public with no NAT and works for
  Fargate only because `assign_public_ip = ENABLED` gives each task ENI a public IP. EC2 instances
  get no public IP there, so they can't reach the ECS/ECR endpoints, never register, and jobs stick
  in `RUNNABLE` (see Troubleshooting). Use the subnets/SG a working EC2 environment uses — those have
  egress (NAT or auto-assigned public IPs).

The EC2 job definitions reuse the same `image_repository`, `execution_role_arn`, `job_role_arn`,
and per-stage environment maps as the Fargate ones (`ec2_prod` tracks the prod toshi overlay,
`ec2_experimental` the test one — ADR-0010). Instance types (`ec2_instance_types`,
default `["optimal"]`), `min_vcpus` (default 0), and allocation strategy default sensibly —
instance-type tuning is tracked in #323.

## Adopting the compute env + queue, creating the job definitions

The compute environment and queue already exist and are **imported**; the two job definitions are
**new** (ADR-0007) and are **created** by apply.

```bash
terraform init
terraform import aws_batch_compute_environment.fargate <compute-environment-name>
terraform import aws_batch_job_queue.fargate <BasicFargate_Q-arn>
terraform plan
```

**After import, `terraform plan` must show only the two `aws_batch_job_definition` resources to
create** (and zero changes to the imported compute env + queue). That clean diff is the proof the
HCL faithfully describes the live compute env/queue. If it shows changes to the imported resources,
adjust `main.tf`/`terraform.tfvars` to match the live config (not the other way around) and re-plan
until only the two creates remain.

### Seed the tags first

The job definitions reference `${image_repository}:prod` / `:experimental`, so those tags must
exist in ECR before the definitions are usable. Seed them once from the current live image (the
digest `Fargate-runzi-opensha-JD` points at), e.g. with `runzi utils promote --source <version-tag>`
for `:prod` and a `runzi utils docker-build` (or a manual retag) for `:experimental`. After apply,
re-running `terraform plan` should show zero changes. (The EC2 job definitions track the *same*
`:prod` / `:experimental` tags, so no extra seeding is needed for them.)

## Creating the EC2 compute env + queue + job definitions (ADR-0008, #322)

Unlike the Fargate compute env/queue (imported), the EC2 resources are **all created fresh** — the
legacy EC2 environments are slated for deletion and we don't import resources we're about to
retire. With the EC2 discovery values filled into `terraform.tfvars`:

```bash
terraform plan   # should add: aws_batch_compute_environment.ec2, aws_batch_job_queue.ec2,
                 #             aws_batch_job_definition.ec2_prod, aws_batch_job_definition.ec2_experimental
terraform apply
```

Smoke-test before retiring anything: submit a small job with a config whose `submission_arg_overrides`
sets `ecs_job_definition: runzi-ec2-JD` (the queue and compute-environment type derive from it), and
confirm it reaches `RUNNING` on EC2.

### Troubleshooting: jobs stuck in RUNNABLE

`RUNNABLE` means Batch accepted the job but no compute instance is available to place it — it waits
indefinitely, it does not time out. Cold start from `min_vcpus = 0` is ~2–5 min; longer means a
problem. Diagnose with:

```bash
# Is the CE scaling, and did any instance join the ECS cluster?
CLUSTER=$(aws batch describe-compute-environments --compute-environments runzi-ec2-CE --region us-east-1 \
  --query 'computeEnvironments[0].ecsClusterArn' --output text)
aws batch describe-compute-environments --compute-environments runzi-ec2-CE --region us-east-1 \
  --query 'computeEnvironments[0].computeResources.{desired:desiredvCpus,max:maxvCpus}'
aws ecs list-container-instances --cluster "$CLUSTER" --region us-east-1
```

- **`desiredvCpus > 0` but `containerInstanceArns` is empty** → instances launch but never register:
  a **networking** problem. Almost always the subnets lack egress to ECS/ECR (the original #322 bug
  was reusing the Fargate public/no-NAT subnet). Fix by pointing `ec2_subnets` / `ec2_security_group_ids`
  at a working EC2 environment's egress-capable subnets/SG. Confirm instances have no public IP and
  the subnet has no NAT route with `aws ec2 describe-instances` / `describe-route-tables`.
- **`desiredvCpus` stays 0** → CE `INVALID`/`DISABLED`, queue not mapped, or the job's vCPU exceeds
  `ec2_max_vcpus`.
- **instances present but job still RUNNABLE** → the job's memory exceeds the instance's *allocatable*
  memory (less than advertised RAM). See `docs/usage/aws_batch.md`.

## Day-to-day workflow

```bash
terraform plan    # review before any change
terraform apply   # apply after review
```

Running jobs are unaffected by `plan`/`import` (state-only operations) and by a clean `apply`
(no actual change to apply). Treat any non-empty `plan` on this root as worth understanding
before applying — these resources back live job submission.

## Retiring the old job definition

The old `Fargate-runzi-opensha-JD` is replaced by `runzi-fargate-JD`. Once nothing resolves it
(runzi's default is repointed and any in-flight submissions have drained), deregister it by hand —
the same manual cleanup ADR-0004 uses for deleted Batch resources. It is not Terraform-managed, so
there is nothing to remove from state.

## Retiring the legacy EC2 environments (ADR-0008, #322)

Once the new `runzi-ec2-*` resources are applied and smoke-tested, retire the superseded EC2
compute environments and queues — `BigLever_*`, `BigLeverOnDemandEC2`, `ToshiHazardPost_*` — **by
hand in the console** (disable → drain running jobs → delete queue → delete compute environment).
They are not Terraform-managed (never imported, since they're slated for deletion), so there's
nothing to remove from state. After retirement, `terraform plan` must remain clean.

## What this root does NOT manage

- The **image content** the job definitions run — that's published via `runzi utils docker-build`
  / `runzi utils promote` moving the `:experimental` / `:prod` ECR tags (ADR-0007). This root owns
  the definition *shape* and which tag it tracks, not the image.
- IAM roles, VPC/subnets/security groups, the ECR repo, Secrets Manager secrets, Cognito — these
  are referenced by ID/name via variables, not created or imported here.
- The Terraform state bucket itself (bootstrapped manually, above).
