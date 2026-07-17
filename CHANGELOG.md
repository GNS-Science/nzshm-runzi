# Changelog

## [Unreleased]

### Changed
- Docker image: smaller and faster to build. Runtime stage installs only its own system deps (git + fonts) instead of copying the entire build-stage `/usr`; Java is now a JRE rather than the full JDK; runzi is installed straight from git (`pip install "runzi @ git+..."`) instead of a working-tree clone; BuildKit pip cache mounts avoid re-downloading the OpenQuake stack on rebuilds; and the build CLI no longer forces `--no-cache` (it uses `--pull` so unchanged layers are reused).

### Removed
- Docker `dev` image/stage and its CLI plumbing (`docker-build --dev`, `runzi --docker-dev`, `dev_locally.md`). Venv isolation removed the need for the editable-install dev image.

## [0.13.0] 2026-07-17

### Changed
- Migrated from bump2version to hatch-vcs versioning
- deps: patch (boto3 1.43.43→1.43.44, botocore transitive); minor: none landable (typer already at latest allowed under `<0.26` cap; llvmlite/numba/pydantic-core blocked by upstream pins); major: numpy 1.26.4→2.4.6 with numba 0.60→0.66, llvmlite 0.43→0.48, and toshi-hazard-post 0.7.1→0.7.3 upgraded together (entangled pins), tzdata 2025.3→2026.2. Skipped: `safety-schemas` (pinned exactly by `safety==3.8.1`), `pandas` (capped `<3` by `solvis==1.3.4`, already latest solvis release).
- deps: patch upgrades (19 pkgs), minor upgrades (37 pkgs incl. `typer` 0.17→0.25), major: `chardet` 5→7 (direct); `cryptography` 48→49, `pymdown-extensions` 10→11, `smart-open` 7→8 (transitive). `typer` capped `<0.26` after smoke testing found it breaks `safety scan`. Skipped: `pandas`/`tzdata`/`numpy` (blocked by `solvis`/`toshi-hazard-post` transitive pins), `safety` 3.8.1 (conflicts with `typer`, kept effectively unchanged).
- Rupture set and inversion report batch defaults: ecs_memory 7000 → 30720, jvm_heap_max 32 → 28: AWS -Xmx becomes 28 G (~75% over the floor, to avoid intermittent OOM).  Move from the EC2 job definition to Fargate (default JD).

### Added
- Fonts in docker build for use by OpenSHA reports
- `runzi reports rupset` and `reports inversion` print General Task ID: <id>, which feeds straight into runzi batch <gt_id> for tracking.
- `scripts/rupset_report_mem_bench.py` drives the RupsetReportJobRunner → build_tasks path to benchmark memeory requirements for rupture set report task.

## [0.12.1] 2026-07-14

## Changed
- Maximum run time for Coulomb rupture set builder and rupture set diags report set to 200 min (was 90)
- Default vCPU, threads, and memory, and job definition for rupture set diags

## [0.12.0] 2026-07-14

### Added
 - Terraform IaC for the AWS Batch Fargate compute environment and `BasicFargate_Q` job queue (`terraform/batch/`); the hand-created resources are adopted via `terraform import`, with `terraform plan` as the drift detector. The job definition stays CLI-managed. See `docs/architecture/adr/0004-aws-batch-iac-terraform.md`.
 - Terraform IaC for runzi's IAM access tiers (`terraform/access/`), migrating the federated Cognito roles to code. See `docs/architecture/adr/0005-runzi-iam-tiers-terraform-migration.md`.
 - Two Terraform-managed Batch job definitions (`runzi-fargate-JD`, `runzi-fargate-experimental-JD`) that track floating ECR image tags (`:prod` / `:experimental`) instead of pinned digests, so they no longer mutate on every deploy. See `docs/architecture/adr/0007-job-definition-terraform-tag-publish.md`.
 - `runzi utils promote` command: publishes an already-built image to the shared prod surface by moving the `:prod` ECR tag (a deliberate, audited step), distinct from the self-serve `:experimental` push.
 - `ec2_subnets` / `ec2_security_group_ids` Terraform variables so the EC2 Batch compute environment uses its own egress-capable subnets/SG (a NAT gateway or auto-assigned public IPs) instead of the Fargate public/no-NAT subnet — without which EC2 instances can't reach ECS/ECR to register and jobs stick in `RUNNABLE`. See `docs/architecture/adr/0008-aws-batch-ec2-compute-environment.md` and the `terraform/batch/README.md` troubleshooting section.
 - Terraform IaC for a single On-Demand EC2 Batch compute environment (`runzi-ec2-CE`), queue (`runzi-ec2-Q`), and two job definitions (`runzi-ec2-JD`, `runzi-ec2-experimental-JD`) — completing the one-Fargate-plus-one-EC2 consolidation. The EC2 definitions track the same floating `:prod` / `:experimental` image tags as their Fargate counterparts; EC2 stays an explicit per-job opt-in (`submission_arg_overrides`), Fargate remains the default. Canonical `EC2_JOB_DEFINITION` / `EC2_EXPERIMENTAL_JOB_DEFINITION` / `EC2_JOB_QUEUE` constants added to `runzi/arguments.py`. Instance-type tuning is deferred to #323. See `docs/architecture/adr/0008-aws-batch-ec2-compute-environment.md` (#322).
 - `runzi batch status <GENERAL_TASK_ID>` — a read-only command that lists the AWS Batch jobs for a submitted task, showing each job's status, run time, creation time, and the swept-argument values that make each job unique. Aimed at users who have no AWS console access (#326, #335).
 - `runzi batch log <JOB_ID>` — downloads a single Batch job's log to a local `<JOB_ID>.log` file (#337).
 - EC2 sizing benchmarks, and their tooling under `scripts/ec2_sizing/`, for the crustal inversion and coulomb rupture-set jobs — used to pick instance families and sizes. See `docs/benchmarks/` and `docs/architecture/adr/0011-*` (#323).
 - `runzi/cli/docker_wrapper.py` now runs as a standalone launcher, so a user can run tasks with only the Docker image + `docker` + `aws` CLI, without installing runzi (`curl` it to `runzi-docker` and run it directly). It is the same file that powers `runzi --docker`; `rich`/`python-dotenv` are optional (with a stdlib `.env` fallback) and `__main__` accepts `--docker-shell` / `--docker-image` / `--docker-dry-run`. Auth uses the lightweight `nshm-toshi-client` (`toshi-auth login` / `aws-creds`). See `docs/usage/docker/run_without_install.md`.

### Changed
 - Inversion and rupture-set builder jobs now run on EC2 by default instead of Fargate, using compute-optimized instances and benchmark-tuned sizes (inversions 8 vCPU / 14000 MiB; rupture-set builds 4 vCPU / 7000 MiB with a 90-minute time limit, up from 60). Fargate stays available as a per-job override. See `docs/architecture/adr/0011-*` and `docs/benchmarks/` (#323).
 - Batch job definitions are now stage-aware: `:prod` definitions authenticate to the production Toshi API and `:experimental` definitions to the test API, so unreviewed images can only write test data. No runzi code change — scientists already choose the definition per job. See `docs/architecture/adr/0010-batch-toshi-stage-per-image-tag.md`.
 - Split `SystemArgs` into `SubmissionArgs` (submitter-only: ECS sizing, job definition, queue/compute env) and `TaskRuntimeArgs` (the small per-task context serialized to the worker). The worker no longer re-validates submission-only fields it never uses, removing a class of submitter↔worker schema-skew crash (and deleting the `freeze_batch_target` workaround). Task modules now declare `default_submission_args`; the shipped config key is `task_runtime_args`. The worker image and submitter must be deployed together. **Breaking:** the config override key `sys_arg_overrides` is renamed `submission_arg_overrides` (a config still using the old key is rejected as an unknown field). See `docs/architecture/adr/0009-submission-vs-runtime-args.md`.
 - AWS Batch job queue and compute-environment type now derive from the chosen job definition: a config only needs to set `ecs_job_definition` (e.g. `runzi-ec2-JD`) and the correct queue + compute type follow automatically, removing the friction (and mis-targeting foot-gun) of keeping all three `submission_arg_overrides` consistent by hand. `ecs_job_queue` / `ecs_compute_environment` remain available as explicit overrides. See `docs/architecture/adr/0008-aws-batch-ec2-compute-environment.md`.
 - Consolidated AWS Batch compute config: tasks now inherit a single default Fargate job definition/queue instead of each hardcoding their own, and `get_ecs_job_config` validates memory/vcpu against the real Fargate size matrix (up to 16 vCPU) via `validate_fargate_resources`, replacing the inline assert table. See `docs/architecture/adr/0003-aws-batch-compute-consolidation.md`.
 - `runzi utils docker-build` no longer registers a Batch job definition; it pushes the image and moves the `:experimental` tag (publishing is now tag-based, not job-definition-registration-based). The `:latest` tag is retired in favour of `:experimental` / `:prod`. The default job definition is repointed to `runzi-fargate-JD`; experimental runs override `ecs_job_definition` to `runzi-fargate-experimental-JD`. Submissions resolve the job definition's tag to a concrete digest at submit time for honest toshi provenance. See `docs/architecture/adr/0007-job-definition-terraform-tag-publish.md`.
 - Removed `batch:RegisterJobDefinition` and `iam:PassRole` from the federated `runzi-admin` role (least privilege): job definitions are now Terraform-owned and tag-tracked, so scientists self-serve publishing by pushing the image, not by registering job definitions. See `docs/architecture/adr/0007-job-definition-terraform-tag-publish.md`.
 - Removed Terraform state (S3) access from the federated `runzi-admin` role (least privilege); Terraform roots run with deployer credentials. See `docs/architecture/adr/0005-runzi-iam-tiers-terraform-migration.md`.
 - Tightened runzi access-tier IAM to least-privilege (substrate vs code): dropped the M2M secret read from the base policy and removed Batch compute-environment/queue provisioning from the federated `runzi-admin` role (now deployer/Terraform-only), keeping image push + job-definition publish self-serve. See `docs/architecture/adr/0006-runzi-access-tier-least-privilege.md`.

### Fixed
 - Failed Java Batch jobs now report FAILED instead of SUCCEEDED, so a failure is no longer silently recorded as a success. Adds a `runzi utils fail-demo` command to reproduce the case (#333).
 - Concurrent EC2 Batch jobs no longer collide on a shared network port; each job now picks its own free port, fixing intermittent inversion failures.
 - Local Java tasks now wait for the Java process to finish starting before connecting to it, fixing occasional connection-refused errors at startup.
 - Stage-incorrect S3 ARNs in the `terraform/access/` base policy: the runzi tiers' data-bucket grant was hardcoded to the `-test` buckets regardless of stage, so the `prod` roles targeted the test buckets. Now resolved per stage via stage-keyed `local.s3_data_buckets` (`prod` → `ths-dataset-prod` / `nzshm22-static-reports`; `test` unchanged). See `docs/architecture/adr/0005-runzi-iam-tiers-terraform-migration.md` (#321).
 - Disabled gql client schema fetching to avoid a `DirectiveLocation` crash against the Toshi API.
 - `runzi --docker` (and the standalone launcher) no longer default to the retired `:latest` ECR tag — which the deploy pipeline never publishes, so a first-run pull with no local image would fail. The no-override default now pulls the published `:prod` image; use `--docker-image` for `:experimental` or a specific version tag. `_maybe_pull` also now honors a fully-qualified `--docker-image` URI verbatim (pulling from the account/region in the URI, or a non-ECR registry) instead of always reconstructing the default ECR reference.

## [0.11.0] 2026-06-10

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
