# Migrate runzi's IAM access-tier roles/policies into runzi/Terraform

## Decision

**The 6 IAM resources that grant runzi's own AWS permission surface move from
`nshm-toshi-api`'s `serverless.yml` (CloudFormation) into `terraform/access/` in this repo:**

- Managed policies: `ToshiRunziBaseManagedPolicy`, `ToshiRunziBatchManagedPolicy`,
  `ToshiRunziAdminManagedPolicy`
- Roles: `ToshiRunziLocalRole`, `ToshiRunziBatchRole`, `ToshiRunziAdminRole`

**Everything else stays in `nshm-toshi-api`, untouched, for now:** the Cognito Identity Pool,
its role attachment, all Cognito groups (including `runzi-local`/`runzi-batch`/`runzi-admin`),
the User Pool and its clients/domain/resource-server, and the M2M secret. These are shared
identity/credential machinery, not runzi's permission surface, and are tracked for a future move
into `nzshm-security` (see Followups) — not this migration.

The two repos stay coupled only by **stable string identifiers**, never hard CloudFormation
exports or Terraform remote state:
- The runzi roles' trust policies reference the Identity Pool **ID** (an input variable, sourced
  from `.env`'s `NZSHM22_TOSHI_COGNITO_IDENTITY_POOL_ID`).
- The Serverless-owned role attachment references the runzi role **ARNs** by `Fn::Sub` string
  (`arn:aws:iam::${AWS::AccountId}:role/toshi-runzi-local-${stage}`, etc.) instead of `!GetAtt`,
  so it no longer depends on the departing role resources.

`terraform/access/` is a new, separate Terraform root from `terraform/batch/`
([0004](0004-aws-batch-iac-terraform.md)) — different resource family, but same state bucket
(`nzshm22-runzi-tfstate`, different key) and the same `us-east-1` provider (IAM is global; the
only region-bound resource in the whole ladder, the Identity Pool, stays in Serverless).

## Two deciding inputs

1. **Each app should own its own permission surface; shared identity infra belongs in a shared
   repo.** The team's end-state is that `nzshm-security` will own the Cognito/Identity-Pool
   machinery used by multiple apps, while each app repo (runzi, others) owns the IAM
   policies/roles specific to its own AWS access. Of the 8 resources making up today's runzi
   ladder, only the 3 policies + 3 roles are unambiguously runzi-specific (they encode runzi's
   own ECR/S3/Batch permissions); the Identity Pool and its role attachment are shared
   credential-federation plumbing serving (at least potentially) more than runzi. Moving the
   shared pieces into runzi now, only to move them again into `nzshm-security` later, is pure
   churn — so this migration takes only the unambiguous slice.
2. **The Identity Pool's role attachment is a 1-per-pool singleton, and splitting it from its
   pool across two IaC tools is the single most dangerous step in any version of this
   migration.** If the pool ever moves, that move owns the attachment too, in one tool, in one
   step — never partially. By leaving the pool *and* its attachment together in Serverless this
   time, that hazard simply doesn't arise: the attachment keeps functioning continuously, and
   only its role *references* change (from `!GetAtt` to equivalent ARN strings), which is a
   value-identical, zero-behavior-change edit.

## Background

`nshm-toshi-api` ADR-003 (`docs/adrs/ADR-003-cognito-permission-model.md` in that repo) already
anticipated splitting "the compute-permission domain (Identity Pool + `runzi-*` roles + batch job
role + compute resources)" into its own stack, but deferred it and envisioned moving the Identity
Pool along with the roles. This ADR narrows that split: only the runzi-specific roles/policies
move now; the Identity Pool stays with the rest of the shared Cognito machinery, all of it bound
for `nzshm-security` together later as a single, atomic move (see Followups) — not split across
this migration and a future one.

None of the 6 moving resources, nor the Identity Pool attachment, carries a `DeletionPolicy`
today. Removing a resource from a CloudFormation template deletes the live resource unless
`DeletionPolicy: Retain` is set *first* — so the migration is staged as
**retain + de-reference → import → de-template**, never the reverse, executed once per stage
(`test`, validated end-to-end, then `prod`).

runzi's own code has **no coupling** to any of these resources — it reads only runtime IDs
(`NZSHM22_TOSHI_COGNITO_*`) from env vars and delegates the actual Cognito federation to
`nshm_toshi_client` (see [0002](0002-aws-auth-decision.md)). It never names the roles, policies,
or groups. This migration is therefore pure infrastructure-ownership change with **no runzi
Python changes** and no operator `.env` changes (the Identity Pool ID is preserved by import,
not recreated).

### Who runs `terraform/access/`

Unlike `terraform/batch/` (run under the federated `runzi-admin` session, which has Batch/ECR/S3
write), `terraform/access/` provisions IAM resources — `iam:CreateRole`, `iam:CreatePolicy`, etc.
— which the `runzi-admin` tier does not (and should not) grant itself. Applying this root
requires **deployer-level AWS credentials**, the same credentials used to run `sls deploy`
against `nshm-toshi-api` today.

## Consequences / deferred obligations

- **The admin policy's import is intentionally NOT zero-diff** — it's the one exception. The
  `CreateJobQueue`/`UpdateJobQueue`/`DeleteJobQueue` and `TerraformStateS3` permissions that
  runzi-admin needs for `terraform/batch/` are authored **only** in `terraform/access/main.tf`;
  they were deliberately removed from `nshm-toshi-api` rather than deployed there just to be
  migrated straight out (they were never part of any deployed `serverless.yml`). So when
  `aws_iam_policy.runzi_admin` is imported, the live policy lacks them and the post-import
  `terraform plan` will show **exactly those additions** — expected, not a faithfulness failure;
  `terraform apply` then creates them. Every other resource still imports zero-diff.
- **The base policy's S3 ARNs are stage-incorrect today** (hardcoded to `-test` buckets
  regardless of stage — flagged in toshi-api's ADR-003). This migration imports that bug
  faithfully rather than fixing it in-flight, to keep the custody transfer itself low-risk and
  verifiable by a zero-diff plan. Fixing it is a deliberate follow-up.
- **Two coordination tickets are required** (one per repo) because the toshi-api side of the
  handoff (`sls deploy` retain/de-reference, then later de-template) is run by the team, not by
  this repo's tooling. See Files for the issues opened.
- **No CI apply** for `terraform/access/` yet — manual, deployer-credentialed runs only, same
  posture as `terraform/batch/`.

## Followups not blocking this decision

- **`nzshm-security` extraction.** Move the Identity Pool, its role attachment, all Cognito
  groups, the User Pool and its clients/domain/resource-server, and the M2M secret out of
  `nshm-toshi-api` into `nzshm-security`, as a single atomic move (avoiding the singleton-split
  hazard described above). At that point, resolve the boundary calls left open by this ADR:
  whether the User Pool itself, the `toshi-readers`/`toshi-writers` groups (toshi-api's own
  access axis, as opposed to runzi's AWS axis), and the M2M client/secret belong in
  `nzshm-security` or stay with `nshm-toshi-api`. Tracked via a `nzshm-security` issue (see Files).
- **Fix the stage-incorrect S3 ARNs** in the base policy once Terraform owns it.
- **CI-driven `terraform apply`** for `terraform/access/`, if/when the team wants it automated.

## Files

- `terraform/access/{versions,backend,providers,variables,main,outputs}.tf`, `README.md` — the
  new Terraform root (this repo).
- `docs/usage/access_tiers.md` — operator-facing description of the now-Terraform-owned ladder
  and its string-coupling to the Serverless-owned Identity Pool/attachment.
- `nshm-toshi-api/serverless.yml` — Retain + role-attachment de-reference (deploy #1), then
  removal of the 6 resources (deploy #2). Deployed by the team, not from this repo.
- `nshm-toshi-api/docs/adrs/ADR-003-cognito-permission-model.md` — status note pointing here.
- GitHub issues: `GNS-Science/nshm-toshi-api` (the per-stage hand-off checklist) and
  `GNS-Science/nzshm-security` (tracking the future shared-infra extraction).
- [0001](0001-cognito-identity-pool-role-mapping.md), [0002](0002-aws-auth-decision.md),
  [0004](0004-aws-batch-iac-terraform.md) — related runzi ADRs.
