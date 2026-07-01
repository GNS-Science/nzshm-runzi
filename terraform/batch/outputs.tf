output "compute_environment_arn" {
  value = aws_batch_compute_environment.fargate.arn
}

output "job_queue_arn" {
  value = aws_batch_job_queue.fargate.arn
}

output "prod_job_definition_arn" {
  value = aws_batch_job_definition.prod.arn
}

output "experimental_job_definition_arn" {
  value = aws_batch_job_definition.experimental.arn
}

output "ec2_compute_environment_arn" {
  value = aws_batch_compute_environment.ec2.arn
}

output "ec2_job_queue_arn" {
  value = aws_batch_job_queue.ec2.arn
}

output "ec2_prod_job_definition_arn" {
  value = aws_batch_job_definition.ec2_prod.arn
}

output "ec2_experimental_job_definition_arn" {
  value = aws_batch_job_definition.ec2_experimental.arn
}
