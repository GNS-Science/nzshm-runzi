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
    --query "Stacks[0].Outputs[?OutputKey=='IdentityPoolId'].OutputValue" --output text
  ```

## Migrating an existing stage (import, don't recreate)

These roles/policies already exist, created by `nshm-toshi-api`'s Serverless stack. Follow this
order **exactly** — reversing it deletes live IAM resources used for active logins:

1. **In `nshm-toshi-api`:** add `DeletionPolicy: Retain` + `UpdateReplacePolicy: Retain` to the 6
   resources, and change `ToshiIdentityPoolRoleAttachment`'s role references from `!GetAtt` to
   `Fn::Sub` ARN strings. `sls deploy --stage <stage>`. (See the issue tracking this in that
   repo.) **Do this before any `terraform import` below.**
2. **Here:** select the workspace, fill `terraform.tfvars`, then:
   ```bash
   terraform init
   terraform import aws_iam_policy.runzi_base   arn:aws:iam::<account-id>:policy/toshi-runzi-base-<stage>
   terraform import aws_iam_policy.runzi_batch  arn:aws:iam::<account-id>:policy/toshi-runzi-batch-<stage>
   terraform import aws_iam_policy.runzi_admin  arn:aws:iam::<account-id>:policy/toshi-runzi-admin-<stage>
   terraform import aws_iam_role.runzi_local  toshi-runzi-local-<stage>
   terraform import aws_iam_role.runzi_batch  toshi-runzi-batch-<stage>
   terraform import aws_iam_role.runzi_admin  toshi-runzi-admin-<stage>
   terraform plan
   ```
   **`terraform plan` must show zero changes — with one expected exception:**
   `aws_iam_policy.runzi_admin` will show the `CreateJobQueue`/`UpdateJobQueue`/`DeleteJobQueue`
   actions and the `TerraformStateS3` statement being **added**. Those are authored only here
   (never deployed via serverless) and runzi-admin needs them for `terraform/batch/` — so the
   plan adding them is correct. `terraform apply` to create them. Any *other* diff means
   `main.tf`/`terraform.tfvars` doesn't match the live resource — fix that (not the live
   resource) before proceeding. See ADR-0005 "Consequences".
3. **In `nshm-toshi-api`:** once the plan above shows only the expected admin-policy additions,
   `terraform apply`, then remove the 6 resource definitions and `sls deploy --stage <stage>`
   again. CloudFormation drops them from the stack; `Retain` keeps the live resources untouched;
   Terraform is now sole owner.
4. Re-run `terraform plan` here once more — it should still be clean (the CloudFormation removal
   shouldn't have touched the now-Terraform-owned resources at all).

Repeat for each stage. **Do `test` first and validate (a `runzi-batch` user can still log in and
submit a job) before touching `prod`.**

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
