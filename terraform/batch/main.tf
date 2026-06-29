# Phase 1 IaC scope: the Fargate compute environment and job queue only.
#
# The job definition (Fargate-runzi-opensha-JD) is deliberately NOT managed here - it is
# re-registered with a new image digest on every `runzi utils docker-build`, which would
# conflict with Terraform ownership. See docs/architecture/aws-batch-iac-terraform.md.
#
# IAM roles, VPC/subnets/security groups, the ECR repo, and secrets are referenced via the
# variables above, not created or imported here - they belong to other systems/owners.

resource "aws_batch_compute_environment" "fargate" {
  compute_environment_name = var.compute_environment_name
  type                     = "MANAGED"

  compute_resources {
    type               = "FARGATE"
    max_vcpus          = var.max_vcpus
    subnets            = var.subnets
    security_group_ids = var.security_group_ids
  }
}

resource "aws_batch_job_queue" "fargate" {
  name     = var.job_queue_name
  state    = "ENABLED"
  priority = var.job_queue_priority

  compute_environment_order {
    order               = 1
    compute_environment = aws_batch_compute_environment.fargate.arn
  }
}
