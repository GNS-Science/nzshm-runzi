# runzi AWS Batch Terraform (Phase 1)

Manages the **Fargate compute environment** and **`BasicFargate_Q` job queue** that runzi
submits AWS Batch jobs to. See
[`docs/architecture/adr/0004-aws-batch-iac-terraform.md`](../../docs/architecture/adr/0004-aws-batch-iac-terraform.md)
for the decision record, including why the job definition is deliberately **not** managed here.

Run everything in this directory (`terraform/batch/`) — it's a standalone Terraform root.

## Prerequisites

- Terraform >= 1.10 (for native S3 state locking via `use_lockfile`).
- AWS credentials with read access to Batch (for discovery/import) and write access to Batch,
  matching whatever account/role you use to operate runzi's AWS Batch resources today.

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

Copy `terraform.tfvars.example` to `terraform.tfvars` and fill these in (gitignored — it's
environment-specific).

## Adopting the existing resources

```bash
terraform init
terraform import aws_batch_compute_environment.fargate <compute-environment-name>
terraform import aws_batch_job_queue.fargate <BasicFargate_Q-arn>
terraform plan
```

**`terraform plan` must show zero changes after import.** That's the proof the HCL faithfully
describes the live resources — nothing will be destroyed or recreated. If it shows a diff, adjust
`main.tf`/`terraform.tfvars` to match the live config (not the other way around) and re-plan
until it's clean.

## Day-to-day workflow

```bash
terraform plan    # review before any change
terraform apply   # apply after review
```

Running jobs are unaffected by `plan`/`import` (state-only operations) and by a clean `apply`
(no actual change to apply). Treat any non-empty `plan` on this root as worth understanding
before applying — these resources back live job submission.

## What this root does NOT manage

- The job definition (`Fargate-runzi-opensha-JD`) — see the ADR for why.
- IAM roles, VPC/subnets/security groups, the ECR repo, Secrets Manager secrets, Cognito — these
  are referenced by ID/name via variables, not created or imported here.
- The Terraform state bucket itself (bootstrapped manually, above).
