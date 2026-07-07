terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Benchmark module (#323 and future instance-type benchmarks). The RESOURCES are ephemeral — stand
# them up with `terraform apply`, run the benchmark, then `terraform destroy` — but the STATE lives in
# S3 (see backend.tf) so cleanup never depends on one person's local disk and concurrent runs are
# lock-safe. Reusable across task types: the module is task-agnostic (a list of instance types); the
# task-specific workload lives in scripts/ec2_sizing/.
