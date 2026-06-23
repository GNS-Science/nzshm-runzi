# State backend for the runzi AWS Batch Terraform root.
#
# The S3 bucket below is NOT managed by this Terraform root - it is a one-time, out-of-band
# bootstrap (see terraform/batch/README.md), the same way the Batch resources themselves were
# hand-created before this root existed. `use_lockfile` enables Terraform's native S3 locking
# (Terraform >= 1.10), so no separate DynamoDB lock table is needed.
#
# Fill in `bucket` (and `key`/`region` if they differ) before running `terraform init`.
terraform {
  backend "s3" {
    bucket       = "nzshm22-runzi-tfstate" # CONFIRM/CREATE - see README.md "State bucket bootstrap"
    key          = "batch/terraform.tfstate"
    region       = "us-east-1"
    use_lockfile = true
  }
}
