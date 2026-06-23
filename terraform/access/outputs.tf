output "role_arns" {
  description = "ARNs of the runzi access-tier roles, for cross-checking against nshm-toshi-api's role-attachment Fn::Sub strings."
  value = {
    local = aws_iam_role.runzi_local.arn
    batch = aws_iam_role.runzi_batch.arn
    admin = aws_iam_role.runzi_admin.arn
  }
}
