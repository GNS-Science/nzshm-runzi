# Build and Deploy Docker Container

The `docker-build` command builds a runzi Docker image capable of running OpenSHA and OpenQuake, pushes it to AWS ECR, and moves the `:experimental` image tag onto it. It does **not** register or modify a Batch job definition — the job definitions are owned by Terraform (`terraform/batch/`) and track floating image tags (`:experimental`, `:prod`), so a freshly-pushed image goes live for *experimental* submissions on their next run. Promoting an image to the shared *prod* surface is a separate, deliberate step: `runzi utils promote` (see below). See [ADR-0007](../../architecture/adr/0007-job-definition-terraform-tag-publish.md).

The build optionally includes the UCERF conversion package, [created by GEM](https://gitlab.openquake.org/hazard/converters/ucerf) which converts OpenSHA inversion solutions to OpenQuake source inputs. You must have a copy of the package in the directory `docker/ucerf`.

## Overview

This script is used to:

- Build a Docker image containing runzi, OpenSHA, and OpenQuake
- Push the image to the AWS Elastic Container Registry (ECR), tagged with an immutable `runzi-<hash>...` version tag and the floating `:experimental` tag

The immutable version tag and `:experimental` share the same digest, so the running image is always traceable back to its git hash. The `:latest` tag has been retired.

## Usage

The script is run via the runzi CLI:

```console
$ runzi utils docker-build [OPTIONS]
```

The script prints the image digest when completed. The digest uniquely identifies the code used to produce hazard realization curves; runzi resolves the relevant job definition's tag to a concrete digest at submit time and records it (`NZSHM22_RUNZI_ECR_DIGEST`) in toshi provenance.

## Promoting to prod

`runzi utils promote` moves the `:prod` tag onto an already-published image, changing the image every default (prod) submission runs. This is the only command that touches the shared prod surface, so it confirms before acting (use `--yes` to skip):

```bash
# promote whatever :experimental currently points at
runzi utils promote

# or promote a specific tested build by its version tag
runzi utils promote --source runzi-abc1234_py3.11_opensha-bf70d35_oq-3.23.4
```

Promotion is a manifest re-tag inside ECR — no rebuild or re-push of layers.

## Required Arguments

The following arguments are required and must be provided either via command line or environment variables:

| Argument | Description |
|----------|-------------|
| `--fatjar-tag` | OpenSHA fatjar tag (e.g., `bf70d35`) |
| `--runzi-gitref` | Git branch, tag, or commit to build from |

## Optional Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--python-version` | Python version | `3.11` |
| `--oq-version` | OpenQuake version | `3.23.4` |
| `--install-converter` | Install UCERF converter | `false` |
| `--region` | AWS region | `us-east-1` |
| `--aws-account-id` | AWS account ID | `461564345538` |
| `--ecr-repo` | ECR repository name | `nzshm22/runzi` |
| `--dockerfile` | Path to Dockerfile | `docker/Dockerfile` |
| `--skip-build` | Skip Docker build | `false` |
| `--skip-push` | Skip ECR push | `false` |

## Environment Variables

You can also configure the script using environment variables:

| Variable | Description |
|----------|-------------|
| `FATJAR_TAG` | OpenSHA fatjar tag |
| `RUNZI_GITREF` | Git branch, tag, or commit |
| `PYTHON_VERSION` | Python version |
| `OQ_VERSION` | OpenQuake version |
| `AWS_REGION` | AWS region |
| `AWS_ACCOUNT_ID` | AWS account ID |
| `ECR_REPO` | ECR repository name |
| `DOCKERFILE` | Path to Dockerfile |

Environment variables take precedence over default values but can be overridden by command line arguments.

## .env File

A `.env` in the project root can also be used to configure the script. Environment variables will take precidence over those set in `.env` file. An example `.env` file:

```bash
# Required
FATJAR_TAG=bf70d35
OQ_VERSION=3.23.4

# Optional
PYTHON_VERSION=3.11
RUNZI_GITREF=main
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=461564345538
ECR_REPO=nzshm22/runzi
```

## Common Use Cases

### Full Deployment

Deploy a new image with all defaults:

```bash
runzi utils docker-build --fatjar-tag bf70d35 --runzi-gitref main
```

Or with environment variables:

```bash
export FATJAR_TAG=bf70d35
export RUNZI_GITREF=main
runzi utils docker-build
```

### Test Build Only

Build the image without pushing (useful for testing):

```bash
runzi utils docker-build --fatjar-tag bf70d35 --runzi-gitref main --skip-push
```

### Specific Versions

Deploy with specific OpenQuake and Python versions:

```bash
runzi utils docker-build \
    --fatjar-tag bf70d35 \
    --runzi-gitref main \
    --oq-version 3.24.0 \
    --python-version 3.11
```

### Deploy Converter

Include the UCERF converter in the image:

```bash
runzi utils docker-build \
    --fatjar-tag bf70d35 \
    --runzi-gitref main \
    --install-converter
```

### Via runzi CLI

```bash
runzi utils docker-build \
    --fatjar-tag bf70d35 \
    --runzi-gitref main
```

## Output

After a successful build, the script outputs:

- Image URI (e.g., `461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi:runzi-abc1234_py3.11_opensha-bf70d35_oq-3.23.4`), also tagged `:experimental`
- Docker digest (e.g., `sha256:5128732f7135120e3d80240587130c122382d5af88226fa87304eec3ea410ef7`)

The image is now live for experimental submissions. Run `runzi utils promote` to publish it to prod.
