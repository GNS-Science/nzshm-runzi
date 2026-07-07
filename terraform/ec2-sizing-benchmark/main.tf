# One pinned, On-Demand EC2 compute environment + queue per instance type, so the #323 Phase 2 family
# comparison can run all types from a single `terraform apply` (and remove them with one `destroy`),
# instead of re-pinning terraform/batch's shared CE and applying once per family.
#
# Jobs still use the existing EC2 job definition (runzi-ec2-experimental-JD); submit_matrix.py routes
# each family's jobs to the matching queue via `--job-queue`. min_vcpus = 0 so idle CEs cost nothing.

locals {
  # "c6i.2xlarge" -> "c6i-2xlarge", a Batch-name-safe suffix.
  safe_name = { for it in var.instance_types : it => replace(it, ".", "-") }
}

resource "aws_batch_compute_environment" "bench" {
  for_each = toset(var.instance_types)

  compute_environment_name = "${var.name_prefix}-${local.safe_name[each.key]}-CE"
  type                     = "MANAGED"
  service_role             = var.batch_service_role_arn != "" ? var.batch_service_role_arn : null

  compute_resources {
    type                = "EC2"
    allocation_strategy = "BEST_FIT_PROGRESSIVE"
    min_vcpus           = 0
    max_vcpus           = var.max_vcpus
    instance_type       = [each.key] # pinned: this CE launches only this instance type
    instance_role       = var.ec2_instance_role_arn
    subnets             = var.subnets
    security_group_ids  = var.security_group_ids
  }

  lifecycle {
    ignore_changes = [compute_resources[0].desired_vcpus]
  }
}

resource "aws_batch_job_queue" "bench" {
  for_each = toset(var.instance_types)

  name     = "${var.name_prefix}-${local.safe_name[each.key]}-Q"
  state    = "ENABLED"
  priority = 1

  compute_environment_order {
    order               = 1
    compute_environment = aws_batch_compute_environment.bench[each.key].arn
  }
}
