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

# ── EC2 compute environment, queue, and job definitions (ADR-0008) ─────────────────────────────
# The EC2 side mirrors the Fargate side for jobs that need a size or instance feature Fargate can't
# provide (EC2 is an explicit per-job opt-in — see runzi.arguments.ComputeEnvironment). One
# On-Demand MANAGED compute environment, one queue, and two job definitions that track the same
# floating :prod / :experimental image tags as the Fargate definitions (docker-build / promote move
# those tags; no EC2-specific image). Instance-type/cost tuning is deferred to #323 —
# instance_type defaults to ["optimal"], letting Batch pick from the C/M/R families.
# See docs/architecture/adr/0008-aws-batch-ec2-compute-environment.md.
resource "aws_batch_compute_environment" "ec2" {
  compute_environment_name = var.ec2_compute_environment_name
  type                     = "MANAGED"
  # Omit to use the Batch service-linked role (AWSServiceRoleForBatch); set only if a custom role is required.
  service_role = var.batch_service_role_arn != "" ? var.batch_service_role_arn : null

  compute_resources {
    type                = "EC2"
    allocation_strategy = var.ec2_allocation_strategy
    min_vcpus           = var.ec2_min_vcpus
    max_vcpus           = var.ec2_max_vcpus
    instance_type       = var.ec2_instance_types
    instance_role       = var.ec2_instance_role_arn
    # EC2 instances need egress to ECS/ECR to register with the cluster, so they use their own
    # subnets/SG — NOT the Fargate ones. The Fargate subnet is public with no NAT and no auto-assign
    # public IP, which works for Fargate (assign_public_ip=ENABLED gives each ENI a public IP) but
    # leaves EC2 instances with no route out, so they never register and jobs stick in RUNNABLE.
    # Discover egress-capable subnets from a working EC2 compute environment (README.md). Empty
    # falls back to the Fargate values.
    subnets            = length(var.ec2_subnets) > 0 ? var.ec2_subnets : var.subnets
    security_group_ids = length(var.ec2_security_group_ids) > 0 ? var.ec2_security_group_ids : var.security_group_ids
  }

  # Batch autoscales desired_vcpus at runtime; ignore it so scaling activity doesn't drift state.
  lifecycle {
    ignore_changes = [compute_resources[0].desired_vcpus]
  }
}

resource "aws_batch_job_queue" "ec2" {
  name     = var.ec2_job_queue_name
  state    = "ENABLED"
  priority = var.ec2_job_queue_priority

  compute_environment_order {
    order               = 1
    compute_environment = aws_batch_compute_environment.ec2.arn
  }
}

locals {
  # EC2 container shape: the Fargate base minus the Fargate-only fields (fargatePlatformConfiguration
  # and networkConfiguration/assignPublicIp). vCPU/memory are resting defaults runzi overrides
  # per-job via containerOverrides; EC2 has no strict Fargate CPU/memory matrix, but the pair must
  # still fit within a launchable instance.
  ec2_container_properties = {
    image            = "${var.image_repository}:PLACEHOLDER" # overridden per-definition below
    executionRoleArn = var.execution_role_arn
    jobRoleArn       = var.job_role_arn != "" ? var.job_role_arn : null

    resourceRequirements = [
      { type = "VCPU", value = var.ec2_default_vcpu },
      { type = "MEMORY", value = var.ec2_default_memory },
    ]

    command = ["--help"]

    environment = [for k, v in var.job_definition_environment : { name = k, value = v }]
  }
}

resource "aws_batch_job_definition" "ec2_prod" {
  name                  = var.ec2_prod_job_definition_name
  type                  = "container"
  platform_capabilities = ["EC2"]

  container_properties = jsonencode(merge(local.ec2_container_properties, {
    image = "${var.image_repository}:${var.prod_image_tag}"
  }))
}

resource "aws_batch_job_definition" "ec2_experimental" {
  name                  = var.ec2_experimental_job_definition_name
  type                  = "container"
  platform_capabilities = ["EC2"]

  container_properties = jsonencode(merge(local.ec2_container_properties, {
    image = "${var.image_repository}:${var.experimental_image_tag}"
  }))
}
