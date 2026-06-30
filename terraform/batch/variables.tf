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

# ── Job definitions (ADR-0007) ────────────────────────────────────────────────────────────────
# Two definitions track floating image tags so they are static (never re-registered on a code
# deploy): the prod definition tracks :prod (moved by `runzi utils promote`), the experimental one
# tracks :experimental (moved by `runzi utils docker-build`). Names match runzi.arguments
# DEFAULT_JOB_DEFINITION / EXPERIMENTAL_JOB_DEFINITION. Their container_properties must replicate the
# live Fargate-runzi-opensha-JD apart from the image reference — discover it before apply (README.md).

variable "prod_job_definition_name" {
  description = "Prod Batch job definition name. Matches runzi.arguments.DEFAULT_JOB_DEFINITION."
  type        = string
  default     = "runzi-fargate-JD"
}

variable "experimental_job_definition_name" {
  description = "Experimental Batch job definition name. Matches runzi.arguments.EXPERIMENTAL_JOB_DEFINITION."
  type        = string
  default     = "runzi-fargate-experimental-JD"
}

variable "image_repository" {
  description = "ECR image repository URI without a tag, e.g. <account>.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi. The definitions append :prod / :experimental."
  type        = string
}

variable "prod_image_tag" {
  description = "Floating tag the prod definition tracks. Moved by `runzi utils promote`."
  type        = string
  default     = "prod"
}

variable "experimental_image_tag" {
  description = "Floating tag the experimental definition tracks. Moved by `runzi utils docker-build`."
  type        = string
  default     = "experimental"
}

variable "execution_role_arn" {
  description = "Fargate task execution role ARN embedded in the job definition (e.g. arn:aws:iam::<account>:role/toshi_batch_ECS_TaskExecution). Discover from the live JD before apply."
  type        = string
}

variable "job_role_arn" {
  description = "Job (task) role ARN the container assumes (reads the M2M secret etc.). Discover from the live JD before apply. Empty to omit."
  type        = string
  default     = ""
}

variable "default_vcpu" {
  description = "Default Fargate vCPU in the job definition. runzi overrides this per-job via containerOverrides at submit time; this is the resting default. Discover from the live JD."
  type        = string
  default     = "8"
}

variable "default_memory" {
  description = "Default Fargate memory (MiB) in the job definition. Overridden per-job by runzi at submit time. Discover from the live JD."
  type        = string
  default     = "30720"
}

variable "job_definition_environment" {
  description = "Static environment variables baked into the job definition (e.g. NZSHM22_TOSHI_M2M_SECRET_ARN, NZSHM22_TOSHI_COGNITO_DOMAIN). Discover from the live JD; per-job runtime env is set by runzi via containerOverrides, not here."
  type        = map(string)
  default     = {}
}

variable "assign_public_ip" {
  description = "Fargate network assignPublicIp (ENABLED/DISABLED). Discover from the live JD."
  type        = string
  default     = "ENABLED"
}
