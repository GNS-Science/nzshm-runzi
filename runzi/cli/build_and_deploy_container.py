"""Deploy docker image to AWS ECR and update Batch job definition."""

import os
import subprocess
from pathlib import Path

import boto3
import typer
from dotenv import load_dotenv
from rich import print as rich_print

load_dotenv()

DEFAULTS = {
    "python_version": os.environ.get("PYTHON_VERSION", "3.11"),
    "oq_version": os.environ.get("OQ_VERSION", "3.23.4"),
    "region": os.environ.get("AWS_REGION", "us-east-1"),
    "aws_account_id": os.environ.get("AWS_ACCOUNT_ID", "461564345538"),
    "ecr_repo": os.environ.get("ECR_REPO", "nzshm22/runzi"),
    "job_definition": os.environ.get("JOB_DEFINITION", "runzi_32GB_8VCPU_JD"),
    "dockerfile": os.environ.get("DOCKERFILE", "docker/Dockerfile"),
}

app = typer.Typer()


def get_git_hash(gitref: str, cwd: Path | None = None) -> str:
    """Resolve gitref to a full commit hash."""
    if cwd is None:
        cwd = Path.cwd()
    result = subprocess.run(
        ["git", "rev-parse", gitref],
        capture_output=True,
        text=True,
        cwd=cwd,
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
    cwd: Path | None = None,
) -> str:
    """Build Docker image and return the full git hash used."""
    if cwd is None:
        cwd = Path.cwd()
    git_hash = get_git_hash(runzi_gitref, cwd)

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

    print("Building Docker image...")
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
) -> tuple[str, str]:
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

    print("Pushing to ECR...")
    subprocess.run(["docker", "push", image_uri], check=True)
    subprocess.run(["docker", "push", latest_uri], check=True)

    print(f"Image pushed: {image_uri}")

    result = subprocess.run(
        ["docker", "inspect", image_uri, "--format={{.RepoDigests}}"],
        capture_output=True,
        text=True,
        check=True,
    )
    image_digest = result.stdout.strip().split("@")[1].replace("]","")

    return image_uri, image_digest


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


@app.command()
def build_and_deploy_container(
    fatjar_tag: str = typer.Option(
        default=os.environ.get("FATJAR_TAG"),
        prompt=True if not os.environ.get("FATJAR_TAG") else False,
        help="OpenSHA fatjar tag",
    ),
    runzi_gitref: str = typer.Option(
        default=os.environ.get("RUNZI_GITREF"),
        prompt=True if not os.environ.get("RUNZI_GITREF") else False,
        help="Git branch, tag, or commit to build",
    ),
    python_version: str = typer.Option(
        default=os.environ.get("PYTHON_VERSION", DEFAULTS["python_version"]),
        help="Python version",
    ),
    oq_version: str = typer.Option(
        default=os.environ.get("OQ_VERSION", DEFAULTS["oq_version"]),
        help="OpenQuake version",
    ),
    install_converter: bool = typer.Option(
        default=False, help="Set to install UCERF converter"
    ),
    region: str = typer.Option(
        default=os.environ.get("AWS_REGION", DEFAULTS["region"]),
        help="AWS region",
    ),
    aws_account_id: str = typer.Option(
        default=os.environ.get("AWS_ACCOUNT_ID", DEFAULTS["aws_account_id"]),
        help="AWS account ID",
    ),
    ecr_repo: str = typer.Option(
        default=os.environ.get("ECR_REPO", DEFAULTS["ecr_repo"]),
        help="ECR repository",
    ),
    job_definition: str = typer.Option(
        default=os.environ.get("JOB_DEFINITION", DEFAULTS["job_definition"]),
        help="Batch job definition",
    ),
    dockerfile: str = typer.Option(
        default=os.environ.get("DOCKERFILE", DEFAULTS["dockerfile"]),
        help="Path to Dockerfile",
    ),
    skip_build: bool = typer.Option(default=False, help="Skip Docker build"),
    skip_push: bool = typer.Option(default=False, help="Skip ECR push"),
    skip_job_update: bool = typer.Option(
        default=False, help="Skip job definition update"
    ),
):
    """Build runzi-opensha Docker image, push to ECR, update Batch job definition."""
    if skip_push:
        skip_job_update = True

    rich_print("[bold]runzi-opensha Docker Deployment[/bold]")
    print()
    print("Arguments:")
    print(f"  python_version: {python_version}")
    print(f"  fatjar_tag: {fatjar_tag}")
    print(f"  runzi_gitref: {runzi_gitref}")
    print(f"  oq_version: {oq_version}")
    print(f"  install_converter: {install_converter}")
    print(f"  region: {region}")
    print(f"  aws_account_id: {aws_account_id}")
    print(f"  ecr_repo: {ecr_repo}")
    print(f"  job_definition: {job_definition}")
    print(f"  dockerfile: {dockerfile}")
    print(f"  skip_build: {skip_build}")
    print(f"  skip_push: {skip_push}")
    print(f"  skip_job_update: {skip_job_update}")
    print()

    dockerfile_path = Path(dockerfile)
    if not dockerfile_path.is_absolute():
        dockerfile_path = Path.cwd() / dockerfile_path

    if not dockerfile_path.exists():
        rich_print(f"[red]Error: Dockerfile not found: {dockerfile_path}[/red]")
        raise typer.Exit(1)

    try:
        if skip_build:
            print("Skipping build (using existing runzi-build:latest)")
            git_hash = get_git_hash(runzi_gitref)
        else:
            git_hash = build_docker_image(
                str(dockerfile_path),
                python_version,
                fatjar_tag,
                runzi_gitref,
                oq_version,
                install_converter,
            )

        ecr_login(region, aws_account_id)

        if not skip_push:
            image_uri, image_digest = tag_and_push_image(
                ecr_repo,
                aws_account_id,
                region,
                git_hash,
                python_version,
                fatjar_tag,
                oq_version,
            )
        else:
            image_uri, image_digest = "<skipped>", "sha256:skipped"

        if not skip_job_update:
            new_job_def_arn = update_job_definition(
                job_definition,
                image_uri,
                region,
            )

        print()
        stages = [
            ("Build", not skip_build),
            ("Push image to ECR", not skip_push),
            ("Update job definition", not skip_job_update),
        ]
        completed = [name for name, done in stages if done]
        rich_print(f"[bold green]Completed {', '.join(completed)}![/bold green]")
        print(f"Image URI: {image_uri}")
        print(f"Image digest: {image_digest}")
        if not skip_job_update:
            print(f"Job Definition: {new_job_def_arn}")
        print()

    except Exception as e:
        rich_print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
