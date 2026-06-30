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
# is `terraform plan` showing zero changes after import.
#
# ONE INTENTIONAL EXCEPTION: aws_iam_policy.runzi_admin keeps its three LIVE statements verbatim
# (the console-edited VisualEditor0/1 + IAMAdmin, preserved exactly so they import zero-diff) and
# appends ONE NEW statement authored only here - BatchQueueAdmin - so the admin policy's import is
# not zero-diff: `terraform plan` shows that added statement, which apply then creates.
# (The live test policy diverged from serverless.yml - hand-edited; see ADR-0005 "Consequences".)
# A `TerraformStateS3` grant was removed - terraform/batch/ runs with deployer creds, so the
# federated runzi-admin role should not hold Terraform-state access (see ADR-0005 followups).

data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
}

# ── Managed policies (the increments) ──────────────────────────────────────────────────────

resource "aws_iam_policy" "runzi_base" {
  name        = "toshi-runzi-base-${var.stage}"
  description = "Base runzi permissions (ECR pull, S3 read/write) shared by all runzi tiers"

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
      # ── Three statements below mirror the LIVE policy verbatim (console-edited; hence the
      #    VisualEditor* Sids). They are preserved exactly so the import is zero-diff for them.
      #    The live admin policy carries hand-applied permissions the serverless.yml never had —
      #    notably iam:PassRole and ECR scoped to nzshm22/* (the real repo) — kept intentionally.
      {
        Sid    = "VisualEditor0"
        Effect = "Allow"
        Action = [
          "batch:DeregisterJobDefinition",
          "batch:CreateComputeEnvironment",
          "batch:DeleteComputeEnvironment",
          "batch:RegisterJobDefinition",
          "batch:UpdateComputeEnvironment",
        ]
        Resource = "*"
      },
      {
        Sid    = "VisualEditor1"
        Effect = "Allow"
        Action = [
          "ecr:CreateRepository",
          "ecr:BatchGetImage",
          "ecr:CompleteLayerUpload",
          "ecr:BatchDeleteImage",
          "ecr:UploadLayerPart",
          "ecr:InitiateLayerUpload",
          "ecr:BatchCheckLayerAvailability",
          "ecr:PutImage",
        ]
        Resource = [
          "arn:aws:ecr:*:*:repository/nzshm22/*",
        ]
      },
      {
        Sid    = "IAMAdmin"
        Effect = "Allow"
        Action = [
          "iam:PassRole",
        ]
        Resource = [
          "arn:aws:iam::${local.account_id}:role/toshi_batch_ECS_TaskExecution",
        ]
      },
      # ── One NEW statement below is a Terraform-era addition (authored only here, never in
      #    serverless). LEAST-PRIVILEGE NOTE: terraform/batch/ is run with DEPLOYER creds (like
      #    terraform/access/), NOT the federated runzi-admin session — so a `TerraformStateS3`
      #    grant (s3 on nzshm22-runzi-tfstate) was deliberately REMOVED here: Terraform-state
      #    access belongs to the deployer, not a Cognito-federated role. The Batch compute-env /
      #    queue admin perms (`BatchAdmin` + this `BatchQueueAdmin`) are the same kind of
      #    provisioning power and are pending the same review (see ADR-0005 followups).
      {
        Sid    = "BatchQueueAdmin"
        Effect = "Allow"
        Action = [
          "batch:CreateJobQueue",
          "batch:UpdateJobQueue",
          "batch:DeleteJobQueue",
        ]
        Resource = "*"
      },
    ]
  })
}

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

  tags = { STAGE = var.stage }
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

  tags = { STAGE = var.stage }
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

  tags = { STAGE = var.stage }
}
