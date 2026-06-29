# Names below match runzi/arguments.py (DEFAULT_JOB_QUEUE, and the compute environment backing
# it) and runzi/job_runner.py's hard-coded Batch region. Keep them in sync if either side changes.

variable "aws_region" {
  description = "AWS region Batch runs in (matches runzi/job_runner.py's hard-coded Batch client region)."
  type        = string
  default     = "us-east-1"
}

variable "compute_environment_name" {
  description = "Name of the existing Fargate compute environment backing BasicFargate_Q. Discover with `aws batch describe-compute-environments` (see README.md) before import."
  type        = string
}

variable "job_queue_name" {
  description = "Name of the existing job queue. Matches runzi.arguments.DEFAULT_JOB_QUEUE."
  type        = string
  default     = "BasicFargate_Q"
}

variable "max_vcpus" {
  description = "Compute environment max vCPUs. Must be high enough for the desired OQ hazard/disagg concurrency at 8 vCPU/job (see docs/architecture/aws-batch-compute-consolidation.md). Set to the live value discovered before import."
  type        = number
}

variable "subnets" {
  description = "Subnet IDs for the Fargate compute environment. Discover from the live compute environment before import."
  type        = list(string)
}

variable "security_group_ids" {
  description = "Security group IDs for the Fargate compute environment. Discover from the live compute environment before import."
  type        = list(string)
}

variable "job_queue_priority" {
  description = "Priority of the job queue. Discover from the live queue before import."
  type        = number
  default     = 1
}
