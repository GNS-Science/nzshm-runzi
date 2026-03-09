# Build and Deploy Docker Container

The `build_and_deploy_container` script builds a runzi Docker image capable of running OpenSHA and OpenQuake, pushes it to AWS ECR, and updates the AWS Batch job definition.

The build optionally includes the UCERF conversion package (created by GEM, https://gitlab.openquake.org/hazard/converters/ucerf) which converts OpenSHA inversion solutions to OpenQuake source inputs. You must have a copy of the package in the directory `docker/ucerf`.

## Overview

This script is used to:

- Build a Docker image containing runzi, OpenSHA, and OpenQuake
- Push the image to the AWS Elastic Container Registry (ECR)
- Update an AWS Batch job definition to use the new image

This is typically used when deploying new versions of the runzi application to AWS Batch.

## Usage

The script can be run via the runzi CLI:

```console
$ runzi utils deploy-docker [OPTIONS]
```

The script will print the image digest when completed. This is used to set the `NZSHM22_RUNZI_ECR_DIGEST` env var used by `toshi-hazard-store` to uniquely identify the code used to produce hazard realization curves.

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
| `--job-definition` | Batch job definition name | `runzi_32GB_8VCPU_JD` |
| `--dockerfile` | Path to Dockerfile | `docker/Dockerfile` |
| `--skip-build` | Skip Docker build | `false` |
| `--skip-push` | Skip ECR push | `false` |
| `--skip-job-update` | Skip job definition update | `false` |

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
| `JOB_DEFINITION` | Batch job definition name |
| `DOCKERFILE` | Path to Dockerfile |

Environment variables take precedence over default values but can be overridden by command line arguments.

## .env File

A `.env` in the project root can also be used to configure the script. Environment variables will take precidence over those set in `.env` file. An example `.env` file:

```bash
# Required
FATJAR_TAG=bf70d35
RUNZI_GITREF=main

# Optional
PYTHON_VERSION=3.11
OQ_VERSION=3.23.4
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=461564345538
ECR_REPO=nzshm22/runzi
JOB_DEFINITION=runzi_32GB_8VCPU_JD
```

## Common Use Cases

### Full Deployment

Deploy a new image with all defaults:

```bash
python scripts/deploy_docker.py --fatjar-tag bf70d35 --runzi-gitref main
```

Or with environment variables:

```bash
export FATJAR_TAG=bf70d35
export RUNZI_GITREF=main
python scripts/deploy_docker.py
```

### Test Build Only

Build the image without pushing (useful for testing):

```bash
python scripts/deploy_docker.py --fatjar-tag bf70d35 --runzi-gitref main --skip-push
```

### Specific Versions

Deploy with specific OpenQuake and Python versions:

```bash
python scripts/deploy_docker.py \
    --fatjar-tag bf70d35 \
    --runzi-gitref main \
    --oq-version 3.24.0 \
    --python-version 3.11
```

### Deploy Converter

Include the UCERF converter in the image:

```bash
python scripts/deploy_docker.py \
    --fatjar-tag bf70d35 \
    --runzi-gitref main \
    --install-converter
```

### Via runzi CLI

```bash
runzi utils deploy-docker \
    --fatjar-tag bf70d35 \
    --runzi-gitref main
```

## Output

After a successful deployment, the script outputs:

- Image URI (e.g., `461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi:runzi-abc1234_py3.11_opensha-bf70d35_oq-3.23.4`)
- Docker digest
- New job definition ARN
- Command to submit a job with the new revision
