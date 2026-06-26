# IAM is a global service - this single, unaliased provider is sufficient. The one region-bound
# resource in the full access-tier ladder, the Cognito Identity Pool, stays in nshm-toshi-api
# (see docs/architecture/adr/0005-runzi-iam-tiers-terraform-migration.md) and is referenced here
# only by its ID (var.identity_pool_id), not provisioned.
provider "aws" {
  region = "us-east-1"
}
