variable "aws_region" {
  description = "AWS region Batch runs in (matches runzi/job_runner.py's hard-coded Batch client region)."
  type        = string
  default     = "us-east-1"
}

variable "name_prefix" {
  description = "Prefix for the throwaway benchmark compute environments and queues."
  type        = string
  default     = "ec2sizing"
}

variable "instance_types" {
  description = <<-EOT
    Instance types to benchmark, one pinned compute environment + queue each. For the #323 Phase 2
    family comparison at 8 vCPU, use the .2xlarge of each family (exact-fit = one job per instance, no
    co-tenancy). The queue for each is named `<name_prefix>-<type with . as ->-Q` (see the `queues`
    output), which submit_matrix.py targets via `--job-queue`.
  EOT
  type        = list(string)
  default = [
    "c6i.2xlarge", "m6i.2xlarge", "r6i.2xlarge", # Intel
    "c6a.2xlarge", "m6a.2xlarge", "r6a.2xlarge", # AMD (same x86 arch, ~10% cheaper)
  ]
}

variable "max_vcpus" {
  description = "Max vCPUs per pinned compute environment (default 64 = up to 8 concurrent 8-vCPU jobs)."
  type        = number
  default     = 64
}

# ── Discovery: use the SAME values as terraform/batch's live EC2 compute environment ──────────────
# Read these from `aws batch describe-compute-environments --compute-environments runzi-ec2-CE`
# (or copy from terraform/batch/terraform.tfvars). EC2 instances need egress to ECS/ECR to register.

variable "ec2_instance_role_arn" {
  description = "ECS instance-profile ARN the EC2 container instances run under (same as terraform/batch)."
  type        = string
}

variable "subnets" {
  description = "Egress-capable subnet IDs (same as terraform/batch's ec2_subnets)."
  type        = list(string)
}

variable "security_group_ids" {
  description = "Security group IDs allowing outbound 443 to ECS/ECR/STS (same as terraform/batch's ec2_security_group_ids)."
  type        = list(string)
}

variable "batch_service_role_arn" {
  description = "Optional Batch service role ARN. Leave empty (\"\") to use the AWSServiceRoleForBatch service-linked role."
  type        = string
  default     = ""
}
