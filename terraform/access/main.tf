# Runzi's own AWS access-tier IAM policies and roles - a cumulative ladder (local ⊂ batch ⊂
# admin) granting STS credentials for ECR pull, S3 report read/write, and AWS Batch
# submit/admin. Faithfully migrated from nshm-toshi-api/serverless.yml
# (ToshiRunzi{Base,Batch,Admin}ManagedPolicy / ToshiRunzi{Local,Batch,Admin}Role) - see
# docs/architecture/adr/0005-runzi-iam-tiers-terraform-migration.md for why only these 6
# resources move here, and why the Cognito Identity Pool + its role attachment stay in
# nshm-toshi-api.
#
# IMPORTANT: keep this file byte-faithful to whatever is actually deployed in
# nshm-toshi-api/serverless.yml at migration/import time for each stage - the success criterion
# is `terraform plan` showing zero changes after import. Do not fold in new permissions here;
# land those as a separate, later change once Terraform owns the resource.

data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
}

# ── Managed policies (the increments) ──────────────────────────────────────────────────────

resource "aws_iam_policy" "runzi_base" {
  name        = "toshi-runzi-base-${var.stage}"
  description = "Base runzi permissions (ECR pull, S3 read/write, M2M secret read) shared by all runzi tiers"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ECRRead"
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
          "ecr:DescribeRepositories",
          "ecr:ListImages",
        ]
        Resource = "*"
      },
      {
        Sid    = "S3ReadWrite"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket",
          "s3:PutObjectAcl",
        ]
        # NOTE: hardcoded to the -test buckets regardless of stage - migrated faithfully from
        # the live (buggy) policy. See ADR 0005 "Fix the stage-incorrect S3 ARNs" followup.
        Resource = [
          "arn:aws:s3:::ths-poc-arrow-test",
          "arn:aws:s3:::ths-poc-arrow-test/*",
          "arn:aws:s3:::nzshm22-static-reports-test",
          "arn:aws:s3:::nzshm22-static-reports-test/*",
        ]
      },
      {
        Sid      = "M2MSecretRead"
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = "arn:aws:secretsmanager:${data.aws_region.current.name}:${local.account_id}:secret:toshi-m2m-*"
      },
    ]
  })
}

resource "aws_iam_policy" "runzi_batch" {
  name        = "toshi-runzi-batch-${var.stage}"
  description = "Incremental runzi-batch permissions (AWS Batch submit/describe); attached on top of the base policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "BatchSubmit"
        Effect = "Allow"
        Action = [
          "batch:SubmitJob",
          "batch:DescribeJobs",
          "batch:ListJobs",
          "batch:TerminateJob",
          "batch:DescribeJobQueues",
          "batch:DescribeComputeEnvironments",
          "batch:DescribeJobDefinitions",
        ]
        Resource = "*"
      },
    ]
  })
}

resource "aws_iam_policy" "runzi_admin" {
  name        = "toshi-runzi-admin-${var.stage}"
  description = "Incremental runzi-admin permissions (Batch + ECR administration); attached on top of the base + batch policies"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "BatchAdmin"
        Effect = "Allow"
        Action = [
          "batch:CreateComputeEnvironment",
          "batch:UpdateComputeEnvironment",
          "batch:DeleteComputeEnvironment",
          "batch:RegisterJobDefinition",
          "batch:DeregisterJobDefinition",
          "batch:CreateJobQueue",
          "batch:UpdateJobQueue",
          "batch:DeleteJobQueue",
        ]
        Resource = "*"
      },
      {
        Sid    = "ECRAdmin"
        Effect = "Allow"
        Action = [
          "ecr:CreateRepository",
          "ecr:PutImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:BatchDeleteImage",
        ]
        Resource = [
          "arn:aws:ecr:*:*:repository/nshm-runzi-*",
        ]
      },
      {
        # Terraform state for terraform/batch/ in nzshm-runzi (S3 backend + native S3 locking,
        # which writes/deletes a "<key>.tflock" object).
        Sid    = "TerraformStateS3"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket",
        ]
        Resource = [
          "arn:aws:s3:::nzshm22-runzi-tfstate",
          "arn:aws:s3:::nzshm22-runzi-tfstate/*",
        ]
      },
    ]
  })
}

data "aws_region" "current" {}

# ── Roles (assumed via the Cognito Identity Pool after login) ─────────────────────────────
#
# All three share the same Cognito-federated trust policy, scoped to var.identity_pool_id (the
# Identity Pool itself lives in nshm-toshi-api - see versions.tf/providers.tf). Each tier
# attaches the base policy plus the increments of all lower tiers, so admin ⊇ batch ⊇ local by
# construction.

data "aws_iam_policy_document" "cognito_federated_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = ["cognito-identity.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "cognito-identity.amazonaws.com:aud"
      values   = [var.identity_pool_id]
    }

    condition {
      test     = "ForAnyValue:StringLike"
      variable = "cognito-identity.amazonaws.com:amr"
      values   = ["authenticated"]
    }
  }
}

resource "aws_iam_role" "runzi_local" {
  name                 = "toshi-runzi-local-${var.stage}"
  description          = "Runzi workstation access (ECR pull, S3 read/write)"
  max_session_duration = 3600
  assume_role_policy   = data.aws_iam_policy_document.cognito_federated_trust.json

  managed_policy_arns = [
    aws_iam_policy.runzi_base.arn,
  ]
}

resource "aws_iam_role" "runzi_batch" {
  name                 = "toshi-runzi-batch-${var.stage}"
  description          = "Runzi batch job access (base + Batch submit)"
  max_session_duration = 3600
  assume_role_policy   = data.aws_iam_policy_document.cognito_federated_trust.json

  managed_policy_arns = [
    aws_iam_policy.runzi_base.arn,
    aws_iam_policy.runzi_batch.arn,
  ]
}

resource "aws_iam_role" "runzi_admin" {
  name                 = "toshi-runzi-admin-${var.stage}"
  description          = "Runzi admin access (base + Batch submit + Batch/ECR admin)"
  max_session_duration = 3600
  assume_role_policy   = data.aws_iam_policy_document.cognito_federated_trust.json

  managed_policy_arns = [
    aws_iam_policy.runzi_base.arn,
    aws_iam_policy.runzi_batch.arn,
    aws_iam_policy.runzi_admin.arn,
  ]
}
