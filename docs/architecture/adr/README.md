# Architecture Decision Records

This directory captures significant, hard-to-reverse architectural decisions for `runzi` — the
*why* behind choices that future maintainers would otherwise have to reverse-engineer from code
or commit history. For a general overview of the codebase (not a decision record), see
[`../architecture.md`](../architecture.md).

## Numbering and filename

Sequential, four-digit, zero-padded: `NNNN-{descriptive-name-in-kebab-case}.md`. Once a number is
assigned it never changes, even if the decision is later superseded — note that in the doc itself
and leave the file in place.

## Index

| # | Title |
|---|---|
| [0001](0001-cognito-identity-pool-role-mapping.md) | Cognito Identity Pool role mapping with multiple User Pool groups |
| [0002](0002-aws-auth-decision.md) | AWS authentication: in-memory Cognito session vs `~/.aws/credentials` |
| [0003](0003-aws-batch-compute-consolidation.md) | AWS Batch compute: consolidate to a single Fargate environment |
| [0004](0004-aws-batch-iac-terraform.md) | AWS Batch IaC: Terraform for the compute environment and queue (Phase 1) |
| [0005](0005-runzi-iam-tiers-terraform-migration.md) | Migrate runzi's IAM access-tier roles/policies into runzi/Terraform |
| [0006](0006-runzi-access-tier-least-privilege.md) | Runzi access-tier least-privilege: substrate vs code |
