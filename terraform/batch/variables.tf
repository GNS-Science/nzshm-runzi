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
  description = "Default Fargate vCPU — the VCPU entry under the live JD's containerProperties.resourceRequirements. runzi overrides this per-job via containerOverrides, so it is only a resting default, but must form a valid Fargate pair with default_memory (see FARGATE_VCPU_MEMORY_MB in runzi/aws/aws.py) or registration fails."
  type        = string
  default     = "8"
}

variable "default_memory" {
  description = "Default Fargate memory (MiB) — the MEMORY entry under the live JD's containerProperties.resourceRequirements. Overridden per-job by runzi; must be valid for default_vcpu on Fargate (e.g. 8 vCPU allows 16384-61440 in 4096 steps). Default 32768 = the historical 32GB_8VCPU size."
  type        = string
  default     = "32768"
}

# Env baked into the job definitions is split across three maps so the :prod and :experimental
# definitions can authenticate to different toshi stages (ADR-0010). job_definition_environment holds
# stage-agnostic vars shared by all four JDs; the two stage overlays below carry the toshi auth pair
# (NZSHM22_TOSHI_M2M_SECRET_ARN + NZSHM22_TOSHI_COGNITO_DOMAIN) and are merged over the shared base.
# Per-job runtime env is set by runzi via containerOverrides, not here.
variable "job_definition_environment" {
  description = "Stage-agnostic environment variables baked into every job definition (e.g. NZSHM22_S3_UPLOAD_WORKERS). The toshi auth pair lives in the per-stage overlays below, not here. Discover from the live JD."
  type        = map(string)
  default     = {}
}

variable "prod_job_definition_environment" {
  description = "Toshi auth env for the :prod job definitions (Fargate + EC2) — the PROD NZSHM22_TOSHI_M2M_SECRET_ARN + NZSHM22_TOSHI_COGNITO_DOMAIN. Merged over job_definition_environment (ADR-0010)."
  type        = map(string)
  default     = {}
}

variable "experimental_job_definition_environment" {
  description = "Toshi auth env for the :experimental job definitions (Fargate + EC2) — the TEST NZSHM22_TOSHI_M2M_SECRET_ARN + NZSHM22_TOSHI_COGNITO_DOMAIN. Merged over job_definition_environment (ADR-0010)."
  type        = map(string)
  default     = {}
}

variable "assign_public_ip" {
  description = "Fargate networkConfiguration.assignPublicIp. Set to ENABLED or DISABLED to match the live JD's containerProperties.networkConfiguration.assignPublicIp. Leave empty (\"\") to omit networkConfiguration entirely — the correct choice when the live JD has no networkConfiguration block (AWS treats absent as DISABLED)."
  type        = string
  default     = ""
}

# ── EC2 compute environment, queue, and job definitions (ADR-0008) ─────────────────────────────
# The single On-Demand EC2 compute environment + queue + two EC2 job definitions that complete the
# one-Fargate-plus-one-EC2 consolidation (#322). Names match runzi.arguments EC2_JOB_DEFINITION /
# EC2_EXPERIMENTAL_JOB_DEFINITION / EC2_JOB_QUEUE. Instance-type/cost tuning is deferred to #323.

variable "ec2_compute_environment_name" {
  description = "Name of the EC2 compute environment to create (single source of truth replacing the retired BigLever* EC2 environments)."
  type        = string
  default     = "runzi-ec2-CE"
}

variable "ec2_instance_role_arn" {
  description = "ECS instance-profile ARN the EC2 container instances run under (e.g. arn:aws:iam::<account>:instance-profile/ecsInstanceRole). Discover from a live EC2 compute environment (`aws batch describe-compute-environments`) before apply."
  type        = string
}

variable "ec2_subnets" {
  description = "Subnets for the EC2 compute environment. EC2 container instances need egress to the ECS/ECR endpoints to register with the cluster (a NAT gateway, or a subnet that auto-assigns public IPs). The Fargate `subnets` (public, no NAT, no auto-assign) do NOT qualify — instances there never register and jobs stick in RUNNABLE. Discover egress-capable subnets from a working EC2 compute environment (`aws batch describe-compute-environments`). Empty falls back to `subnets`."
  type        = list(string)
  default     = []
}

variable "ec2_security_group_ids" {
  description = "Security group IDs for the EC2 compute environment (must allow outbound 443 to ECS/ECR/STS). Discover from a working EC2 compute environment. Empty falls back to `security_group_ids`."
  type        = list(string)
  default     = []
}

variable "ec2_instance_types" {
  description = "Instance types/families Batch may launch. \"optimal\" lets Batch choose from the C/M/R families to fit each job. Instance-type optimization is tracked separately in #323."
  type        = list(string)
  default     = ["optimal"]
}

variable "ec2_min_vcpus" {
  description = "Minimum vCPUs kept running. 0 scales the environment to zero when idle (no standing EC2 cost)."
  type        = number
  default     = 0
}

variable "ec2_max_vcpus" {
  description = "Maximum vCPUs the EC2 compute environment may scale to. Set from the retired BigLever environment's maxvCpus (or the desired concurrency) before apply."
  type        = number
}

variable "ec2_allocation_strategy" {
  description = "How Batch selects instance types from the pool. BEST_FIT_PROGRESSIVE (recommended for On-Demand) falls back across types so jobs don't stall waiting on one type; BEST_FIT is cheapest-only but can stall."
  type        = string
  default     = "BEST_FIT_PROGRESSIVE"
}

variable "batch_service_role_arn" {
  description = "Optional Batch service role ARN for the EC2 compute environment. Leave empty (\"\") to use the AWSServiceRoleForBatch service-linked role (the usual choice)."
  type        = string
  default     = ""
}

variable "ec2_job_queue_name" {
  description = "Name of the EC2 job queue. Matches runzi.arguments.EC2_JOB_QUEUE."
  type        = string
  default     = "runzi-ec2-Q"
}

variable "ec2_job_queue_priority" {
  description = "Priority of the EC2 job queue."
  type        = number
  default     = 1
}

variable "ec2_prod_job_definition_name" {
  description = "Prod EC2 Batch job definition name. Matches runzi.arguments.EC2_JOB_DEFINITION."
  type        = string
  default     = "runzi-ec2-JD"
}

variable "ec2_experimental_job_definition_name" {
  description = "Experimental EC2 Batch job definition name. Matches runzi.arguments.EC2_EXPERIMENTAL_JOB_DEFINITION."
  type        = string
  default     = "runzi-ec2-experimental-JD"
}

variable "ec2_default_vcpu" {
  description = "Default EC2 vCPU resting value (runzi overrides per-job via containerOverrides). EC2 has no strict Fargate CPU/memory matrix, but the pair must fit a launchable instance."
  type        = string
  default     = "8"
}

variable "ec2_default_memory" {
  description = "Default EC2 memory (MiB) resting value (runzi overrides per-job). Must fit within a launchable instance alongside ec2_default_vcpu."
  type        = string
  default     = "32768"
}
