terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Throwaway benchmark module (#323 Phase 2): local state on purpose. Stand up the pinned compute
# environments with `terraform apply`, run the benchmark, then `terraform destroy` to remove them all.
# Nothing here is long-lived, so it deliberately does NOT share the terraform/batch S3 backend.
