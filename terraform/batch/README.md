# runzi AWS Batch Terraform

Manages the **Fargate compute environment**, the **`BasicFargate_Q` job queue**, and the two
**job definitions** (`runzi-fargate-JD`, `runzi-fargate-experimental-JD`) that runzi submits AWS
Batch jobs to. See
[`docs/architecture/adr/0004-aws-batch-iac-terraform.md`](../../docs/architecture/adr/0004-aws-batch-iac-terraform.md)
(compute env + queue) and
[`docs/architecture/adr/0007-job-definition-terraform-tag-publish.md`](../../docs/architecture/adr/0007-job-definition-terraform-tag-publish.md)
(job definitions via floating image tags) for the decision records.

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
must behave identically apart from the tagged image:

```bash
aws batch describe-job-definitions --job-definition-name Fargate-runzi-opensha-JD \
  --status ACTIVE --region us-east-1
```

From its `containerProperties`, note → `execution_role_arn` (`executionRoleArn`), `job_role_arn`
(`jobRoleArn`), `default_vcpu` / `default_memory` (`resourceRequirements`), `assign_public_ip`
(`networkConfiguration.assignPublicIp`), and the static `environment` entries →
`job_definition_environment`. Set `image_repository` to the ECR repo URI **without** a tag.

Copy `terraform.tfvars.example` to `terraform.tfvars` and fill these in (gitignored — it's
environment-specific).

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
re-running `terraform plan` should show zero changes.

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

## What this root does NOT manage

- The **image content** the job definitions run — that's published via `runzi utils docker-build`
  / `runzi utils promote` moving the `:experimental` / `:prod` ECR tags (ADR-0007). This root owns
  the definition *shape* and which tag it tracks, not the image.
- IAM roles, VPC/subnets/security groups, the ECR repo, Secrets Manager secrets, Cognito — these
  are referenced by ID/name via variables, not created or imported here.
- The Terraform state bucket itself (bootstrapped manually, above).
