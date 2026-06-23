output "compute_environment_arn" {
  value = aws_batch_compute_environment.fargate.arn
}

output "job_queue_arn" {
  value = aws_batch_job_queue.fargate.arn
}
