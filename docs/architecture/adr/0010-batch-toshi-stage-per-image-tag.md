# Couple toshi stage (prod/test) to the Batch image-tag axis

## Decision

**The `:prod` Batch job definitions authenticate to the PROD toshi environment; the `:experimental`
job definitions authenticate to the TEST toshi environment.** The toshi auth pair
(`NZSHM22_TOSHI_M2M_SECRET_ARN` + `NZSHM22_TOSHI_COGNITO_DOMAIN`) is baked into each job definition's
container `environment`, so "which toshi stage a job writes to" is now selected by *which job
definition* a scientist runs — the same choice that already selects the image tag (`:prod` via
`runzi utils promote`, `:experimental` via `runzi utils docker-build`).

In `terraform/batch`, the single `job_definition_environment` map is split into three:

| variable | consumed by | holds |
|---|---|---|
| `job_definition_environment` | all four JDs | stage-agnostic vars (e.g. `NZSHM22_S3_UPLOAD_WORKERS`) |
| `prod_job_definition_environment` | `prod`, `ec2_prod` | PROD toshi secret ARN + Cognito domain |
| `experimental_job_definition_environment` | `experimental`, `ec2_experimental` | TEST toshi secret ARN + Cognito domain |

Each JD's `environment` is `merge(job_definition_environment, <stage overlay>)`, derived in a `locals`
block (`prod_environment` / `experimental_environment`) so a stage-agnostic var cannot drift between
the two.

## Two deciding inputs

1. **A container env var holds exactly one value, and runzi never injects it.** The toshi client reads
   the fixed name `NZSHM22_TOSHI_M2M_SECRET_ARN` inside the container at runtime;
   [0009](0009-submission-vs-runtime-args.md) made M2M auth the job definition's responsibility, and
   `tests/test_get_ecs_job_config.py` / `tests/test_docker_wrapper.py` assert runzi never forwards it.
   So supporting prod cannot be a runtime selection in runzi — a job definition must carry the prod
   pair. Reusing the existing `:prod`/`:experimental` JD axis needs **zero runzi code change**: the
   `ecs_job_definition` submission arg already selects the definition.

2. **The coupling is a desired guardrail.** Binding stage to the image tag means unreviewed
   (`:experimental`) images can only write to the test toshi environment; only a deliberately promoted
   (`:prod`) image writes to prod. The accepted trade-off is that code-version and data-stage become
   one axis: there is no path to run a promoted image against test, or experimental code against prod.
   Neither is needed today; if that changes, a real stage axis (separate JDs or a workspace-
   parameterized module like `terraform/access`) would be required instead.

## Consequences / deferred obligations

- **The prod secret's read grant lives outside this repo.** The container reads the secret under
  `job_role_arn` / `execution_role_arn` = `arn:aws:iam::461564345538:role/toshi_batch_ECS_TaskExecution`,
  which is **not** managed here (`terraform/batch/main.tf` header). That role must be granted
  `secretsmanager:GetSecretValue` on the **prod** secret ARN (in addition to test), in whatever system
  owns it (likely `nshm-toshi-api`), or `:prod` jobs fail auth at runtime. `terraform/access` grants no
  secretsmanager permission ([0006](0006-runzi-access-tier-least-privilege.md)), so nothing changes there.
- **`apply` re-registers all four job definitions** with the new per-stage `environment`. No queues or
  compute environments change. The gitignored `terraform.tfvars` must supply the prod ARN + domain.

## Files

- `terraform/batch/variables.tf` — `job_definition_environment` re-described as stage-agnostic;
  new `prod_job_definition_environment` / `experimental_job_definition_environment` (both `map(string)`,
  default `{}`).
- `terraform/batch/main.tf` — `locals.prod_environment` / `locals.experimental_environment`;
  `environment` removed from the shared `base_container_properties` / `ec2_container_properties` and
  set per-JD in the four `aws_batch_job_definition` resources.
- `terraform/batch/terraform.tfvars` — three-map form (prod overlay = prod toshi, experimental overlay
  = the previous test values).
- `terraform/batch/terraform.tfvars.example` — documents the three-map shape.
- [0007](0007-job-definition-terraform-tag-publish.md) — the `:prod`/`:experimental` tag axis this reuses.
