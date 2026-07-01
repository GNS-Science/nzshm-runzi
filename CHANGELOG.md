# Changelog

## [Unreleased]

### Added
 - Terraform IaC for the AWS Batch Fargate compute environment and `BasicFargate_Q` job queue (`terraform/batch/`); the hand-created resources are adopted via `terraform import`, with `terraform plan` as the drift detector. The job definition stays CLI-managed. See `docs/architecture/adr/0004-aws-batch-iac-terraform.md`.
 - Terraform IaC for runzi's IAM access tiers (`terraform/access/`), migrating the federated Cognito roles to code. See `docs/architecture/adr/0005-runzi-iam-tiers-terraform-migration.md`.
 - Two Terraform-managed Batch job definitions (`runzi-fargate-JD`, `runzi-fargate-experimental-JD`) that track floating ECR image tags (`:prod` / `:experimental`) instead of pinned digests, so they no longer mutate on every deploy. See `docs/architecture/adr/0007-job-definition-terraform-tag-publish.md`.
 - `runzi utils promote` command: publishes an already-built image to the shared prod surface by moving the `:prod` ECR tag (a deliberate, audited step), distinct from the self-serve `:experimental` push.
 - `ec2_subnets` / `ec2_security_group_ids` Terraform variables so the EC2 Batch compute environment uses its own egress-capable subnets/SG (a NAT gateway or auto-assigned public IPs) instead of the Fargate public/no-NAT subnet — without which EC2 instances can't reach ECS/ECR to register and jobs stick in `RUNNABLE`. See `docs/architecture/adr/0008-aws-batch-ec2-compute-environment.md` and the `terraform/batch/README.md` troubleshooting section.
 - Terraform IaC for a single On-Demand EC2 Batch compute environment (`runzi-ec2-CE`), queue (`runzi-ec2-Q`), and two job definitions (`runzi-ec2-JD`, `runzi-ec2-experimental-JD`) — completing the one-Fargate-plus-one-EC2 consolidation. The EC2 definitions track the same floating `:prod` / `:experimental` image tags as their Fargate counterparts; EC2 stays an explicit per-job opt-in (`sys_arg_overrides`), Fargate remains the default. Canonical `EC2_JOB_DEFINITION` / `EC2_EXPERIMENTAL_JOB_DEFINITION` / `EC2_JOB_QUEUE` constants added to `runzi/arguments.py`. Instance-type tuning is deferred to #323. See `docs/architecture/adr/0008-aws-batch-ec2-compute-environment.md` (#322).

### Changed
 - Consolidated AWS Batch compute config: tasks now inherit a single default Fargate job definition/queue instead of each hardcoding their own, and `get_ecs_job_config` validates memory/vcpu against the real Fargate size matrix (up to 16 vCPU) via `validate_fargate_resources`, replacing the inline assert table. See `docs/architecture/adr/0003-aws-batch-compute-consolidation.md`.
 - `runzi utils docker-build` no longer registers a Batch job definition; it pushes the image and moves the `:experimental` tag (publishing is now tag-based, not job-definition-registration-based). The `:latest` tag is retired in favour of `:experimental` / `:prod`. The default job definition is repointed to `runzi-fargate-JD`; experimental runs override `ecs_job_definition` to `runzi-fargate-experimental-JD`. Submissions resolve the job definition's tag to a concrete digest at submit time for honest toshi provenance. See `docs/architecture/adr/0007-job-definition-terraform-tag-publish.md`.
 - Removed `batch:RegisterJobDefinition` and `iam:PassRole` from the federated `runzi-admin` role (least privilege): job definitions are now Terraform-owned and tag-tracked, so scientists self-serve publishing by pushing the image, not by registering job definitions. See `docs/architecture/adr/0007-job-definition-terraform-tag-publish.md`.
 - Removed Terraform state (S3) access from the federated `runzi-admin` role (least privilege); Terraform roots run with deployer credentials. See `docs/architecture/adr/0005-runzi-iam-tiers-terraform-migration.md`.
 - Tightened runzi access-tier IAM to least-privilege (substrate vs code): dropped the M2M secret read from the base policy and removed Batch compute-environment/queue provisioning from the federated `runzi-admin` role (now deployer/Terraform-only), keeping image push + job-definition publish self-serve. See `docs/architecture/adr/0006-runzi-access-tier-least-privilege.md`.

### Fixed
 - Stage-incorrect S3 ARNs in the `terraform/access/` base policy: the runzi tiers' data-bucket grant was hardcoded to the `-test` buckets regardless of stage, so the `prod` roles targeted the test buckets. Now resolved per stage via stage-keyed `local.s3_data_buckets` (`prod` → `ths-dataset-prod` / `nzshm22-static-reports`; `test` unchanged). See `docs/architecture/adr/0005-runzi-iam-tiers-terraform-migration.md` (#321).
 - Disabled gql client schema fetching to avoid a `DirectiveLocation` crash against the Toshi API.

## [0.11.0] 2026-10-06

### Added
 - Store disaggregation realizations in toshi-hazard-store dataset
 - Validate all tasks before running to fail early
 - --docker top-level flag to route any runzi command through a local Docker container, plus --dev build mode and dev_locally.md docs
 - NZSHM22_OQ_VENV and NZSHM22_OQ_DATADIR environment variables for locating the OpenQuake venv and HDF5 datastore directory

### Changed
 - M2M auth config (`NZSHM22_TOSHI_M2M_SECRET_ARN`, `NZSHM22_TOSHI_COGNITO_DOMAIN`) is no longer forwarded from the local host into AWS Batch container environments; these must now be supplied by the Batch job definition. Local job submission uses Scientist (login) credentials exclusively.
 - Upgrade nshm-toshi-client
 - Use Cognito JWT authentication for Toshi API
 - Forward NZSHM22_TOSHI_COGNITO_IDENTITY_POOL_ID into the local --docker container (newly supported by nshm-toshi-client)
 - Delegate Cognito AWS-credentials federation to nshm_toshi_client.aws.get_aws_session (runzi keeps only the fallback to default boto3 chain)
 - Upgrade dependencies (gitpython 3.1.47 → 3.1.49, fixes CVE-2026-44244)
 - Docker image now splits OpenQuake and runzi into separate venvs (/opt/oq-venv, /opt/runzi-venv)
 - UCERF converter (oq_opensha_convert_task) now runs in oq-venv via subprocess, decoupling runzi from OpenQuake imports
 - Renamed CLI command utils container → utils docker-build
 - NZSHM22_TOSHI_API_ENABLED is no longer baked into the Docker image; set explicitly in AWS Batch job config and forwarded from host on local --docker runs
 - oq-convert output zip is now written to WORK_PATH instead of being buried in a downloads/ subdirectory
 - Container runs as host UID

## [0.10.1] 2026-03-30

### Changed
 - Updated nzhsm-hazlab and nzshm-common dependencies to take advantage of fix to deserialization of CodedLocation.
 - Improved documentation to include missing env vars and correct command for running docker locally
 - Updated toshi-hazard-store to fix windows build problem due to lancedb

### Added
 - Save task arguments for disaggregation to toshiAPI.

## [0.10.0] 2026-03-12

### Changed
 - `NZSHM22_SCRIPT_CLUSTER_MODE` environment variable replaced by `--cluster-mode` CLI option
 - Updated documentation to reflect `--cluster-mode` CLI argument

### Added
 - Tests for `--cluster-mode` CLI option (`tests/test_cli_cluster_mode.py`)

### Removed
 - `NZSHM22_SCRIPT_CLUSTER_MODE` environment variable support

## [0.9.2] 2026-03-11

### Added
 - Shared validator module `runzi/tasks/validators.py` with `all_or_none`, `exactly_one`, `at_most_one`, and `resolve_path` helpers
 - Tests for all shared validators (`tests/test_validators.py`)
 - `ModuleWithDefaultSysArgs` protocol in `runzi/protocols.py` for task modules that expose `default_system_args`

### Changed
 - Refactored inline validation logic in inversion, coulomb, and hazard task modules to use shared validators
 - Refactored task factories and job runner to use `ModuleWithDefaultSysArgs` protocol instead of untyped module references

## [0.9.1] 2026-03-10

### Changed
 - Improved docker build with UCERF converter option
 - Documentation for building and running docker image
 - Reduced size of docker image

### Added
 - Script for building and deploying docker image
 
### Removed
 - OpenQuake example input files

## [0.9.0] 2026-03-03

### Changed
 - Complete refactor of job configuration and execution
   - Pydantic models for verification of input data
   - Simpler pattern for extending to new task types
   - JSON config files are now validated before submission
   - CLI restructured into subcommands
 - Modernization of python dev standards (pyproject.toml, type hints, etc.)

### Added
 - Sideload paleoseismic recurrence interval
 - Sideload custom fault models
 - Sideload named faults

### Removed
 - python3.9 support

## [0.1.0] 2025-*

### Added
- Initial documentation
- Development toolchain and workflows
- Expand user paths for files specified in hazard config file
- Hazard Task: docker image hash
- Classes for specifying input arguments to scripts.

### Changed
- Hazard and disaggregation job configuration and parsing of sites handled by `nzhsm-model`
- Hazard realizations written to arrow/parquet dataset with `toshi-hazard-store`
- General Task: logic trees, location file, hazard config are uploaded as files
- Hazard Task: logic trees, and hazard config are stored as json

### Removed
 - Deleted unused automation scripts
 - Moved deprecated automation scripts to arkive
