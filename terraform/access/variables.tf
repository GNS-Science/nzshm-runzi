# Select the stage with `terraform workspace select <stage>` before plan/apply - it drives every
# resource name below (toshi-runzi-{base,batch,admin}-${var.stage}, etc.) and must match the
# nshm-toshi-api stage you're migrating. See README.md "Stages (Terraform workspaces)".
variable "stage" {
  description = "Deployment stage suffix, must equal terraform.workspace (e.g. \"test\", \"prod\")."
  type        = string

  validation {
    condition     = var.stage == terraform.workspace
    error_message = "var.stage must equal the selected terraform workspace - run `terraform workspace select ${var.stage}` first."
  }
}

variable "identity_pool_id" {
  description = <<-EOT
    Cognito Identity Pool ID for this stage (e.g. "us-east-1:xxxxxxxx-xxxx-...").
    Sourced from .env's NZSHM22_TOSHI_COGNITO_IDENTITY_POOL_ID for this stage, or from the
    nshm-toshi-api CloudFormation stack output `IdentityPoolId`
    (`aws cloudformation describe-stacks --stack-name nzshm22-toshi-api-<stage>`).
    The Identity Pool itself is NOT managed here - only referenced, by ID, in the runzi roles'
    trust policies.
  EOT
  type        = string
}
