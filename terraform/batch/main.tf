# IaC scope: the Fargate compute environment, job queue, and the two job definitions.
#
# ADR-0007 brought the job definitions under Terraform by pointing them at a floating image *tag*
# (:prod / :experimental) instead of a pinned digest, so they no longer mutate on every
# `runzi utils docker-build` and no longer conflict with Terraform ownership. The image content a
# definition runs changes by moving its tag in ECR (docker-build moves :experimental, promote moves
# :prod); the definition itself stays static. See
# docs/architecture/adr/0007-job-definition-terraform-tag-publish.md.
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

# ── Job definitions (ADR-0007) ────────────────────────────────────────────────────────────────
# Both definitions share one container shape and differ only in the floating image tag they track.
# vCPU/memory here are resting defaults; runzi overrides them per-job via containerOverrides at
# submit time (runzi/aws/aws.py). container_properties must replicate the live Fargate-runzi-opensha-JD
# apart from the tagged image — discover and reconcile it before apply (README.md).
locals {
  # Only emit networkConfiguration when assign_public_ip is set; an empty value omits the block
  # entirely, matching a live JD that has no networkConfiguration (AWS treats absent as DISABLED).
  # It is not overridable per-job, so the JD-level value governs at runtime — keep it faithful.
  network_configuration = var.assign_public_ip != "" ? {
    networkConfiguration = { assignPublicIp = var.assign_public_ip }
  } : {}

  base_container_properties = merge({
    image            = "${var.image_repository}:PLACEHOLDER" # overridden per-definition below
    executionRoleArn = var.execution_role_arn
    jobRoleArn       = var.job_role_arn != "" ? var.job_role_arn : null

    # Resting defaults only — runzi overrides VCPU/MEMORY per-job via containerOverrides. They must
    # still be a valid Fargate pair or registration fails (see FARGATE_VCPU_MEMORY_MB in aws.py).
    resourceRequirements = [
      { type = "VCPU", value = var.default_vcpu },
      { type = "MEMORY", value = var.default_memory },
    ]

    # runzi always overrides command at submit time; a non-empty default keeps the definition valid.
    command = ["--help"]

    environment                  = [for k, v in var.job_definition_environment : { name = k, value = v }]
    fargatePlatformConfiguration = { platformVersion = "LATEST" }
  }, local.network_configuration)
}

resource "aws_batch_job_definition" "prod" {
  name                  = var.prod_job_definition_name
  type                  = "container"
  platform_capabilities = ["FARGATE"]

  container_properties = jsonencode(merge(local.base_container_properties, {
    image = "${var.image_repository}:${var.prod_image_tag}"
  }))
}

resource "aws_batch_job_definition" "experimental" {
  name                  = var.experimental_job_definition_name
  type                  = "container"
  platform_capabilities = ["FARGATE"]

  container_properties = jsonencode(merge(local.base_container_properties, {
    image = "${var.image_repository}:${var.experimental_image_tag}"
  }))
}
