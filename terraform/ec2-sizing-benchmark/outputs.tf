output "queues" {
  description = "Map of instance_type -> Batch job queue name; pass each to submit_matrix.py --job-queue."
  value       = { for it in var.instance_types : it => aws_batch_job_queue.bench[it].name }
}
