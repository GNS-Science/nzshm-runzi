# runzi AWS access-tier Terraform

Manages runzi's own IAM permission surface: the 3 managed policies + 3 roles forming the
cumulative `local ⊂ batch ⊂ admin` ladder. See
[`docs/architecture/adr/0005-runzi-iam-tiers-terraform-migration.md`](../../docs/architecture/adr/0005-runzi-iam-tiers-terraform-migration.md)
for the decision record — including why the Cognito Identity Pool and its role attachment stay
in `nshm-toshi-api` rather than moving here.

Run everything in this directory (`terraform/access/`) — it's a standalone Terraform root,
separate from [`terraform/batch/`](../batch/) (different resource family, same state bucket).

## Who runs this

**Deployer-level AWS credentials are required** — this root provisions IAM (`iam:CreateRole`,
`iam:CreatePolicy`, etc.), which the federated `runzi-admin` session does **not** grant itself
(by design: an access tier shouldn't be able to create more access tiers). Use the same
credentials that run `sls deploy` against `nshm-toshi-api` today.

## Stages (Terraform workspaces)

This root uses **Terraform workspaces**, one per stage, instead of separate state keys — `test`
and `prod` share `backend.tf`'s bucket/key but get independent state via the workspace:

```bash
terraform workspace new test   # first time only
terraform workspace select test
```

`var.stage` must equal the selected workspace (enforced by a `variable` validation in
`variables.tf`) — this is the guard against the costly mistake of applying `prod` values while
sitting in the `test` workspace, or vice versa. Always run `terraform workspace show` before
`plan`/`apply` if you're unsure which one is active.

## Inputs

Copy `terraform.tfvars.example` to `terraform.tfvars` (gitignored) and fill in per stage:

- `stage` — must match the selected workspace.
- `identity_pool_id` — the Cognito Identity Pool ID for this stage. Get it from `.env`'s
  `NZSHM22_TOSHI_COGNITO_IDENTITY_POOL_ID`, or from the `nshm-toshi-api` stack:
  ```bash
  aws cloudformation describe-stacks --stack-name nzshm22-toshi-api-<stage> \
    --region ap-southeast-2 \
    --query "Stacks[0].Outputs[?OutputKey=='IdentityPoolId'].OutputValue" --output text
  ```
  (The stack and the Identity Pool are in `ap-southeast-2`, not the IAM/Batch `us-east-1`.)

## Migrating an existing stage (import, don't recreate)

These roles/policies already exist, created by `nshm-toshi-api`'s Serverless stack, so the stage
is **migrated** (retain → import → de-template), not created from scratch. The full procedure —
each step paired with an AWS-CLI validation gate that proves nothing changed except what was
meant to — lives in **[`MIGRATION_RUNBOOK.md`](MIGRATION_RUNBOOK.md)**. Follow it end to end (it
uses the read-only [`scripts/snapshot-access-tiers.sh`](scripts/snapshot-access-tiers.sh) helper
to snapshot-and-`diff` at each checkpoint). Do `test` first and validate before touching `prod`.

The short version: deploy #1 (Retain + de-reference) in `nshm-toshi-api` → `terraform import` the
6 resources here and confirm a clean `plan` (one expected exception: the admin policy gains the
`CreateJobQueue`/`UpdateJobQueue`/`DeleteJobQueue` `BatchQueueAdmin` grant that lives only in
Terraform) → `terraform apply tfplan` (a saved `plan -out`) → deploy #2 (de-template) in
`nshm-toshi-api`. Order matters — reversing it deletes live IAM resources used for active logins.

## Day-to-day workflow (after migration)

```bash
terraform workspace select <stage>
terraform plan
terraform apply
```

## What this root does NOT manage

- The Cognito Identity Pool and its role attachment — stay in `nshm-toshi-api`, referenced here
  only by ID (`var.identity_pool_id`).
- The Cognito User Pool, clients, domain, resource server, and all Cognito groups (including
  `runzi-local`/`runzi-batch`/`runzi-admin`) — also stay in `nshm-toshi-api`.
- The M2M secret — stays in `nshm-toshi-api`; the base policy here references it only by a
  wildcard ARN string (`secret:toshi-m2m-*`), not a hard dependency.
