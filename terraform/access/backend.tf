# State backend for the runzi IAM access-tier Terraform root.
#
# Shares the same state bucket as terraform/batch/ (bootstrapped out-of-band, NOT managed by
# either root - see terraform/batch/README.md), under a different key so the two roots' state
# never collide. `use_lockfile` enables Terraform's native S3 locking (Terraform >= 1.10).
#
# State is partitioned per stage by Terraform WORKSPACE (test/prod), not by a separate key per
# stage - see README.md "Stages (Terraform workspaces)".
terraform {
  backend "s3" {
    bucket       = "nzshm22-runzi-tfstate"
    key          = "access/terraform.tfstate"
    region       = "us-east-1"
    use_lockfile = true
  }
}
