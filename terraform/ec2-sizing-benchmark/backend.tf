# State backend for the EC2 sizing benchmark root (#323 and future instance-type benchmarks).
#
# Shares the same state bucket as terraform/batch/ and terraform/access/ (bootstrapped out-of-band,
# NOT managed by any root - see terraform/batch/README.md "State bucket bootstrap"), under its own key
# so it never collides with the production roots. `use_lockfile` enables Terraform's native S3 locking
# (Terraform >= 1.10), so concurrent applies are safe and no separate DynamoDB lock table is needed.
#
# The RESOURCES are still ephemeral (apply before a benchmark, destroy after) - S3 state only makes
# that state durable and shared, so cleanup never depends on one person's local disk and two
# benchmarkers can't clobber each other. For simultaneous benchmarks, use a Terraform WORKSPACE to
# partition state (see README.md).
terraform {
  backend "s3" {
    bucket       = "nzshm22-runzi-tfstate"
    key          = "benchmark/ec2-sizing.tfstate"
    region       = "us-east-1"
    use_lockfile = true
  }
}
