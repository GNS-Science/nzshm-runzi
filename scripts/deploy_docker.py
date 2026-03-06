#!/usr/bin/env python3
"""
Script to build runzi-opensha Docker image, push to AWS ECR, and update Batch job definition.

Usage:
    python scripts/deploy_docker.py \
        --fatjar-tag bf70d35 \
        --runzi-gitref main \
        --oq-version 3.23.4

Or with environment variables:
    FATJAR_TAG=bf70d35 RUNZI_GITREF=main OQ_VERSION=3.23.4 python scripts/deploy_docker.py
"""

import argparse
import base64
import os
import re
import subprocess
import sys
from pathlib import Path

import boto3
from dotenv import load_dotenv

DEFAULTS = {
    "python_version": "3.11",
    "oq_version": "3.23.4",
    "region": "us-east-1",
    "aws_account_id": "461564345538",
    "ecr_repo": "nzshm22/runzi",
    "job_definition": "runzi_32GB_8VCPU_JD",
    "dockerfile": "docker/Dockerfile",
}


def get_git_hash(gitref: str) -> str:
    """Resolve gitref to a full commit hash."""
    result = subprocess.run(
        ["git", "rev-parse", gitref],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to resolve gitref '{gitref}': {result.stderr.strip()}"
        )
    return result.stdout.strip()[:7]


def build_docker_image(
    dockerfile: str,
    python_version: str,
    fatjar_tag: str,
    runzi_gitref: str,
    oq_version: str,
    install_converter: bool = False,
) -> str:
    """Build Docker image and return the full git hash used."""
    git_hash = get_git_hash(runzi_gitref)

    dockerfile_path = Path(dockerfile)
    dockerfile_dir = dockerfile_path.parent.resolve()

    build_cmd = [
        "docker",
        "build",
        "--no-cache",
        "-f",
        str(dockerfile_path.name),
        "--build-arg",
        f"PYTHON_VERSION={python_version}",
        "--build-arg",
        f"FATJAR_TAG={fatjar_tag}",
        "--build-arg",
        f"RUNZI_GITREF={git_hash}",
        "--build-arg",
        f"OQ_VERSION={oq_version}",
    ]
    if install_converter:
        build_cmd.extend(["--build-arg", "INSTALL_CONVERTER=Y"])
    build_cmd.extend(
        [
            "-t",
            "runzi-build:latest",
            ".",
        ]
    )

    print(f"Building Docker image...")
    print(f"  Dockerfile: {dockerfile}")
    print(f"  Build context: {dockerfile_dir}")
    print(f"  PYTHON_VERSION: {python_version}")
    print(f"  FATJAR_TAG: {fatjar_tag}")
    print(f"  RUNZI_GITREF: {runzi_gitref} -> {git_hash}")
    print(f"  OQ_VERSION: {oq_version}")

    result = subprocess.run(build_cmd, cwd=dockerfile_dir)
    if result.returncode != 0:
        raise RuntimeError("Docker build failed")

    return git_hash


def ecr_login(region: str, aws_account_id: str) -> None:
    """Login to ECR using AWS CLI pipeline."""
    print("Logging into ECR...")
    registry = f"{aws_account_id}.dkr.ecr.{region}.amazonaws.com"
    subprocess.run(
        f"aws ecr get-login-password --region {region} | docker login --username AWS --password-stdin {registry}",
        shell=True,
        check=True,
    )


def tag_and_push_image(
    ecr_repo: str,
    aws_account_id: str,
    region: str,
    git_hash: str,
    python_version: str,
    fatjar_tag: str,
    oq_version: str,
) -> str:
    """Tag and push image to ECR. Returns the new image URI."""
    registry = f"{aws_account_id}.dkr.ecr.{region}.amazonaws.com"

    version_tag = (
        f"runzi-{git_hash}_py{python_version}_opensha-{fatjar_tag}_oq-{oq_version}"
    )
    image_uri = f"{registry}/{ecr_repo}:{version_tag}"
    latest_uri = f"{registry}/{ecr_repo}:latest"

    print(f"Tagging image as {version_tag}...")
    subprocess.run(["docker", "tag", "runzi-build:latest", image_uri], check=True)
    subprocess.run(["docker", "tag", "runzi-build:latest", latest_uri], check=True)

    print(f"Pushing to ECR...")
    subprocess.run(["docker", "push", image_uri], check=True)
    subprocess.run(["docker", "push", latest_uri], check=True)

    print(f"Image pushed: {image_uri}")

    result = subprocess.run(
        ["docker", "inspect", image_uri, "--format={{.RepoDigests}}"],
        capture_output=True,
        text=True,
        check=True,
    )
    digest = result.stdout.strip()
    print(f"Digest: {digest}")

    return image_uri


def update_job_definition(
    job_definition: str,
    image_uri: str,
    region: str,
) -> str:
    """Update existing job definition with new image. Returns new job definition ARN."""
    print(f"Updating job definition '{job_definition}' with new image...")

    batch_client = boto3.client("batch", region_name=region)

    response = batch_client.describe_job_definitions(
        jobDefinitionName=job_definition,
        status="ACTIVE",
        maxResults=1,
    )

    if not response.get("jobDefinitions"):
        raise RuntimeError(f"No active job definition found: {job_definition}")

    current_def = response["jobDefinitions"][0]
    current_revision = current_def["revision"]
    current_arn = current_def["jobDefinitionArn"]
    current_parameters = current_def["parameters"]

    print(f"Current revision: {current_revision}")
    print(f"Current ARN: {current_arn}")

    container_props = current_def["containerProperties"]
    container_props["image"] = image_uri

    response = batch_client.register_job_definition(
        jobDefinitionName=job_definition,
        type="container",
        parameters=current_parameters,
        containerProperties=container_props,
    )

    new_arn = response["jobDefinitionArn"]
    new_revision = response.get("revision", "?")

    print(f"New job definition: {new_arn}")
    print(f"New revision: {new_revision}")

    return new_arn


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Build runzi-opensha Docker image, push to ECR, update Batch job definition"
    )
    parser.add_argument(
        "--python-version",
        default=os.environ.get("PYTHON_VERSION", DEFAULTS["python_version"]),
        help=f"Python version (default: {DEFAULTS['python_version']})",
    )
    parser.add_argument(
        "--fatjar-tag",
        default=os.environ.get("FATJAR_TAG"),
        required="FATJAR_TAG" not in os.environ,
        help="OpenSHA fatjar tag",
    )
    parser.add_argument(
        "--runzi-gitref",
        default=os.environ.get("RUNZI_GITREF"),
        required="RUNZI_GITREF" not in os.environ,
        help="Git branch, tag, or commit to build",
    )
    parser.add_argument(
        "--oq-version",
        default=os.environ.get("OQ_VERSION", DEFAULTS["oq_version"]),
        required="OQ_VERSION" not in os.environ,
        help=f"OpenQuake version (default: {DEFAULTS['oq_version']})",
    )
    parser.add_argument(
        "--install-converter",
        action="store_true",
        help="Set to install UCERF converter",
    )
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION", DEFAULTS["region"]),
        help=f"AWS region (default: {DEFAULTS['region']})",
    )
    parser.add_argument(
        "--aws-account-id",
        default=os.environ.get("AWS_ACCOUNT_ID", DEFAULTS["aws_account_id"]),
        help=f"AWS account ID for ECR (default: {DEFAULTS['aws_account_id']})",
    )
    parser.add_argument(
        "--ecr-repo",
        default=os.environ.get("ECR_REPO", DEFAULTS["ecr_repo"]),
        help=f"ECR repository name (default: {DEFAULTS['ecr_repo']})",
    )
    parser.add_argument(
        "--job-definition",
        default=os.environ.get("JOB_DEFINITION", DEFAULTS["job_definition"]),
        help=f"Batch job definition to update (default: {DEFAULTS['job_definition']})",
    )
    parser.add_argument(
        "--dockerfile",
        default=DEFAULTS["dockerfile"],
        help=f"Path to Dockerfile (default: {DEFAULTS['dockerfile']})",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip Docker build (use existing runzi-build:latest image)",
    )
    parser.add_argument(
        "--skip-push",
        action="store_true",
        help="Skip ECR push (for testing)",
    )
    parser.add_argument(
        "--skip-job-update",
        action="store_true",
        help="Skip job definition update",
    )

    args = parser.parse_args()

    if args.skip_push:
        args.skip_job_update = True

    print("=" * 60)
    print("runzi-opensha Docker Deployment")
    print("=" * 60)
    print()
    print("Arguments:")

    for arg, value in vars(args).items():
        print(f"  {arg}: {value}")
    print()

    dockerfile = Path(args.dockerfile)
    if not dockerfile.is_absolute():
        dockerfile = Path(__file__).parent.parent / dockerfile

    if not dockerfile.exists():
        print(f"Error: Dockerfile not found: {dockerfile}")
        sys.exit(1)

    try:
        if args.skip_build:
            print("Skipping build (using existing runzi-build:latest)")
            git_hash = get_git_hash(args.runzi_gitref)
        else:
            git_hash = build_docker_image(
                str(dockerfile),
                args.python_version,
                args.fatjar_tag,
                args.runzi_gitref,
                args.oq_version,
                args.install_converter,
            )

        ecr_login(args.region, args.aws_account_id)

        if not args.skip_push:
            image_uri = tag_and_push_image(
                args.ecr_repo,
                args.aws_account_id,
                args.region,
                git_hash,
                args.python_version,
                args.fatjar_tag,
                args.oq_version,
            )
        else:
            image_uri = "<skipped>"

        if not args.skip_job_update:
            new_job_def_arn = update_job_definition(
                args.job_definition,
                image_uri,
                args.region,
            )

        print()
        print("=" * 60)
        print("Deployment complete!")
        print("=" * 60)
        print(f"Image URI: {image_uri}")
        if not args.skip_job_update:
            print(f"Job Definition: {new_job_def_arn}")
            version_match = re.search(r":(\d+)$", new_job_def_arn)
            if version_match:
                revision = version_match.group(1)
                print(
                    f"Submit job with: --job-definition {args.job_definition}:{revision}"
                )
        print()

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
