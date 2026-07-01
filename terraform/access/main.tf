# Runzi's own AWS access-tier IAM policies and roles - a cumulative ladder (local ⊂ batch ⊂
# admin) granting STS credentials for ECR pull, S3 report read/write, and AWS Batch
# submit + code publish. Originally migrated from nshm-toshi-api/serverless.yml
# (ToshiRunzi{Base,Batch,Admin}ManagedPolicy / ToshiRunzi{Local,Batch,Admin}Role) - see
# docs/architecture/adr/0005-runzi-iam-tiers-terraform-migration.md for why only these 6
# resources live here, and why the Cognito Identity Pool + its role attachment stay in
# nshm-toshi-api.
#
# LEAST-PRIVILEGE MODEL (substrate vs code) - see
# docs/architecture/adr/0006-runzi-access-tier-least-privilege.md and
# docs/architecture/adr/0007-job-definition-terraform-tag-publish.md:
# aws_iam_policy.runzi_admin grants only CODE/PUBLISH power: push the runzi image to ECR (ECRPush).
# Publishing is tag-based - docker-build moves the :experimental tag, promote moves :prod - so
# scientists no longer register job definitions; ADR-0007 removed batch:RegisterJobDefinition
# (JobDefPublish) and the iam:PassRole (IAMAdmin) it only existed to support. The job definitions
# themselves are SUBSTRATE: owned by terraform/batch/ (DEPLOYER creds), tracking floating tags.
# Compute-environment/job-queue admin and Terraform state are likewise NOT here.

locals {
  # Data buckets the runzi tiers read/write. Names do NOT follow a <root>-<stage> convention
  # (standardizing them has a large blast radius — out of scope, see #321), so encode them per
  # stage explicitly rather than interpolating var.stage. This is the stage-keyed-locals fallback
  # blessed by ADR-0005.
  s3_data_buckets = {
    test = ["ths-poc-arrow-test", "nzshm22-static-reports-test"]
    prod = ["ths-dataset-prod", "nzshm22-static-reports"]
  }
  s3_data_bucket_arns = flatten([
    for b in local.s3_data_buckets[var.stage] :
    ["arn:aws:s3:::${b}", "arn:aws:s3:::${b}/*"]
  ])
}

# ── Managed policies (the increments) ──────────────────────────────────────────────────────

resource "aws_iam_policy" "runzi_base" {
  name = "toshi-runzi-base-${var.stage}"
  # Description kept verbatim (it still says "M2M secret read") on purpose: aws_iam_policy.description
  # is ForceNew, so changing it would destroy+recreate this policy — which is attached to all three
  # runzi roles. The M2MSecretRead *statement* is removed from the document below (see ADR-0006);
  # the stale word in the description is the lesser evil vs. a replace of a live, attached policy.
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
        # Stage-correct data-bucket ARNs (see local.s3_data_buckets). Fixes the previously
        # hardcoded -test buckets (#321 / ADR-0005 deferred obligation).
        Resource = local.s3_data_bucket_arns
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
      # ── Code/publish power only (see ADR-0006, ADR-0007). Publishing is tag-based: docker-build
      #    pushes the image + moves :experimental, promote moves :prod (both ECR PutImage). The
      #    Terraform-owned job definitions track those tags, so runzi-admin no longer needs
      #    batch:RegisterJobDefinition or the iam:PassRole it required. ECR is scoped to nzshm22/*.
      {
        Sid    = "ECRPush"
        Effect = "Allow"
        Action = [
          "ecr:BatchGetImage",
          "ecr:CompleteLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:InitiateLayerUpload",
          "ecr:BatchCheckLayerAvailability",
          "ecr:PutImage",
        ]
        Resource = [
          "arn:aws:ecr:*:*:repository/nzshm22/*",
        ]
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
