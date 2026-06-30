This describes the IAM permission ladder a scientist's AWS session gets after `toshi-auth
login`, depending on their Cognito group. It is the operator-facing companion to the decision
recorded in
[`docs/architecture/adr/0005-runzi-iam-tiers-terraform-migration.md`](../architecture/adr/0005-runzi-iam-tiers-terraform-migration.md).

# The ladder: local ⊂ batch ⊂ admin

Every authenticated scientist belongs to exactly one `runzi-*` Cognito group
(`runzi-local`/`runzi-batch`/`runzi-admin`), which the Identity Pool maps to one of three IAM
roles. Each tier is cumulative — built by composing managed policies, so a higher tier can never
drift below a lower one:

| Tier | Role | Managed policies attached | Grants |
|---|---|---|---|
| `local` | `toshi-runzi-local-<stage>` | base | ECR pull, S3 report read/write |
| `batch` | `toshi-runzi-batch-<stage>` | base + batch | + AWS Batch submit/describe/terminate |
| `admin` | `toshi-runzi-admin-<stage>` | base + batch + admin | + publish: ECR image push (to `nzshm22/*`). **Not** infra provisioning or job-definition registration — compute environments, queues, and the job definitions are deployer/Terraform-only. |

The split follows a **substrate-vs-code** model (see
[ADR-0006](../architecture/adr/0006-runzi-access-tier-least-privilege.md) and
[ADR-0007](../architecture/adr/0007-job-definition-terraform-tag-publish.md)): scientists self-serve
*code* by pushing the runzi **image** via the federated tiers, while *substrate* (compute
environments, queues, the job definitions, IAM, state, capacity) is provisioned only by the deployer
via Terraform. Publishing is tag-based — `runzi utils docker-build` moves the `:experimental` tag and
`runzi utils promote` moves `:prod`, and the Terraform-owned job definitions track those tags — so
`runzi-admin` no longer needs `batch:RegisterJobDefinition` or `iam:PassRole` (removed in ADR-0007).
The M2M secret is read by the Batch container's own task role, not these federated user roles.

If a user is in more than one `runzi-*` group, the **highest tier wins** — see
[ADR-0001](../architecture/adr/0001-cognito-identity-pool-role-mapping.md) for the role-mapping
rule ordering that makes this work (most-privileged-first).

# What's managed where

This ladder spans two repos, coupled only by **stable string identifiers** (no hard
cross-stack exports):

- **`nzshm-runzi`, `terraform/access/`** (this repo) — the 3 managed policies + 3 IAM roles
  above. This is runzi's own permission surface. See
  [`terraform/access/README.md`](../../terraform/access/README.md) for the operator runbook.
- **`nshm-toshi-api`, `serverless.yml`** — the Cognito Identity Pool, its role attachment (the
  group→role mapping), the User Pool, clients, and all Cognito groups (including the three
  `runzi-*` groups themselves). These are shared identity/credential machinery, not runzi's
  permission surface, and are slated for an eventual move into `nzshm-security`.
  - The runzi roles' trust policies reference the Identity Pool **by ID** (a Terraform variable).
  - The role attachment references the runzi role **ARNs by string** (not by CloudFormation
    `!GetAtt`), so it doesn't depend on the resources that moved here.

# Operator tasks

- **Add a user to a tier:** unchanged — still done in `nshm-toshi-api` (`auth/create_users.py`),
  since the groups live there.
- **Change what a tier can do:** edit the corresponding policy in `terraform/access/main.tf`
  (this repo), then `terraform plan`/`apply` with deployer-level credentials — see
  [`terraform/access/README.md`](../../terraform/access/README.md).
- **Change which tier a group maps to, or add a new tier:** still done in `nshm-toshi-api`'s
  `ToshiIdentityPoolRoleAttachment`, since the attachment lives there.

# History

Before the migration recorded in ADR-0005, all of the above (including the 3 policies + 3 roles)
lived together in `nshm-toshi-api`'s `serverless.yml`, originally designed under that repo's
[ADR-003](https://github.com/GNS-Science/nshm-toshi-api/blob/main/docs/adrs/ADR-003-cognito-permission-model.md)
(the cumulative-ladder design, and the most-privileged-first rule-ordering fix). The IAM
policies/roles moved to this repo; the rest is tracked for a future move into `nzshm-security`.

The per-stage hand-off (with AWS-CLI validation at each step) is documented in
[`terraform/access/MIGRATION_RUNBOOK.md`](../../terraform/access/MIGRATION_RUNBOOK.md).
