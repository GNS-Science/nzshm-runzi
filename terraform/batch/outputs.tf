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
