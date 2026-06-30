"""Build the runzi image, push it to ECR, and manage the experimental/prod floating tags.

The Batch job definitions are owned by Terraform (`terraform/batch/`) and track stable image
**tags** (`:experimental`, `:prod`), not image digests, so publishing never re-registers a job
definition. `docker-build` moves `:experimental` onto a freshly-pushed image (self-serve); `promote`
moves `:prod` onto an already-published digest (a deliberate, audited change to the shared prod
surface). See `docs/architecture/adr/0007-job-definition-terraform-tag-publish.md`.
"""

import subprocess
from pathlib import Path

import boto3
import typer
from dotenv import load_dotenv
from rich import print as rich_print

load_dotenv()

app = typer.Typer()

#: Floating ECR tags the Terraform-owned job definitions resolve to.
EXPERIMENTAL_TAG = "experimental"
PROD_TAG = "prod"


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
        raise RuntimeError(f"Failed to resolve gitref '{gitref}': {result.stderr.strip()}")
    return result.stdout.strip()[:7]


def build_docker_image(
    dockerfile: str,
    python_version: str,
    fatjar_tag: str,
    runzi_gitref: str,
    oq_version: str,
    install_converter: bool = False,
    dev: bool = False,
    cwd: Path | None = None,
) -> str:
    """Build Docker image and return the full git hash used."""
    if cwd is None:
        cwd = Path.cwd()
    git_hash = get_git_hash(runzi_gitref, cwd)

    dockerfile_path = Path(dockerfile)
    dockerfile_dir = dockerfile_path.parent.resolve()

    image_tag = "runzi-build:dev" if dev else "runzi-build:latest"

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
    if dev:
        build_cmd.extend(["--target", "dev"])
    build_cmd.extend(["-t", image_tag, "."])

    print("Building Docker image...")
    print(f"  Dockerfile: {dockerfile}")
    print(f"  Build context: {dockerfile_dir}")
    print(f"  PYTHON_VERSION: {python_version}")
    print(f"  FATJAR_TAG: {fatjar_tag}")
    print(f"  RUNZI_GITREF: {runzi_gitref} -> {git_hash}")
    print(f"  OQ_VERSION: {oq_version}")
    print(f"  Image tag: {image_tag}")
    if dev:
        print("  Target: dev (editable install, local-only)")

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
    """Tag and push the image to ECR under the immutable version tag and the :experimental tag.

    The immutable ``runzi-<hash>_py..._oq-...`` tag is the audit anchor (it shares the digest with
    whatever floating tag points at it); ``:experimental`` is the floating tag the experimental job
    definition tracks. ``:prod`` is moved separately by ``promote``, never here. Returns the version
    image URI and its digest.
    """
    registry = f"{aws_account_id}.dkr.ecr.{region}.amazonaws.com"

    version_tag = f"runzi-{git_hash}_py{python_version}_opensha-{fatjar_tag}_oq-{oq_version}"
    image_uri = f"{registry}/{ecr_repo}:{version_tag}"
    experimental_uri = f"{registry}/{ecr_repo}:{EXPERIMENTAL_TAG}"

    print(f"Tagging image as {version_tag} and :{EXPERIMENTAL_TAG}...")
    subprocess.run(["docker", "tag", "runzi-build:latest", image_uri], check=True)
    subprocess.run(["docker", "tag", "runzi-build:latest", experimental_uri], check=True)

    print("Pushing to ECR...")
    subprocess.run(["docker", "push", image_uri], check=True)
    subprocess.run(["docker", "push", experimental_uri], check=True)

    print(f"Image pushed: {image_uri} (also tagged :{EXPERIMENTAL_TAG})")

    result = subprocess.run(
        ["docker", "inspect", image_uri, "--format={{.RepoDigests}}"],
        capture_output=True,
        text=True,
        check=True,
    )
    image_digest = result.stdout.strip().split("@")[1].replace("]", "")

    return image_uri, image_digest


def retag_image(
    ecr_repo: str,
    region: str,
    source_tag: str,
    target_tag: str,
) -> str:
    """Move ``target_tag`` onto the image manifest already tagged ``source_tag`` in ECR.

    This is a manifest re-tag inside ECR (no pull/rebuild): it copies the existing image's manifest
    under a new tag, so ``source_tag`` and ``target_tag`` end up on the same digest. Returns the
    digest the target tag now points at.
    """
    ecr_client = boto3.client("ecr", region_name=region)

    response = ecr_client.batch_get_image(
        repositoryName=ecr_repo,
        imageIds=[{"imageTag": source_tag}],
    )
    images = response.get("images", [])
    if not images:
        raise RuntimeError(f"No image tagged '{source_tag}' in repository '{ecr_repo}'")

    image = images[0]
    manifest = image["imageManifest"]
    source_digest = image["imageId"].get("imageDigest", "unknown")

    try:
        ecr_client.put_image(
            repositoryName=ecr_repo,
            imageManifest=manifest,
            imageTag=target_tag,
        )
    except ecr_client.exceptions.ImageAlreadyExistsException:
        # :target_tag already points at this exact manifest — nothing to move.
        print(f":{target_tag} already points at {source_digest}; no change.")

    return source_digest


@app.command()
def build_and_deploy_container(
    fatjar_tag: str = typer.Option(..., envvar="FATJAR_TAG", prompt=True, help="OpenSHA fatjar tag"),
    runzi_gitref: str = typer.Option("main", envvar="RUNZI_GITREF", help="Git branch, tag, or commit to build"),
    python_version: str = typer.Option("3.11", envvar="PYTHON_VERSION", help="Python version"),
    oq_version: str = typer.Option(..., envvar="OQ_VERSION", prompt=True, help="OpenQuake version"),
    install_converter: bool = typer.Option(default=False, help="Set to install UCERF converter"),
    dev: bool = typer.Option(
        default=False, help="Build dev image (editable install, local-only; skips ECR push and job update)"
    ),
    region: str = typer.Option("us-east-1", envvar="AWS_REGION", help="AWS region"),
    aws_account_id: str = typer.Option("461564345538", envvar="AWS_ACCOUNT_ID", help="AWS account ID"),
    ecr_repo: str = typer.Option("nzshm22/runzi", envvar="ECR_REPO", help="ECR repository"),
    dockerfile: str = typer.Option("docker/Dockerfile", envvar="DOCKERFILE", help="Path to Dockerfile"),
    skip_build: bool = typer.Option(default=False, help="Skip Docker build"),
    skip_push: bool = typer.Option(default=False, help="Skip ECR push"),
):
    """Build the runzi image, push it to ECR, and move the :experimental tag onto it.

    Does NOT touch the prod job definition: the experimental Batch job definition tracks the
    :experimental tag, so the new image goes live for experimental submissions on its next run.
    Use `runzi utils promote` to publish a tested image to the shared prod surface.
    """
    if dev:
        skip_push = True

    rich_print("[bold]runzi-opensha Docker Deployment[/bold]")
    print()
    print("Arguments:")
    print(f"  python_version: {python_version}")
    print(f"  fatjar_tag: {fatjar_tag}")
    print(f"  runzi_gitref: {runzi_gitref}")
    print(f"  oq_version: {oq_version}")
    print(f"  install_converter: {install_converter}")
    print(f"  dev: {dev}")
    print(f"  region: {region}")
    print(f"  aws_account_id: {aws_account_id}")
    print(f"  ecr_repo: {ecr_repo}")
    print(f"  dockerfile: {dockerfile}")
    print(f"  skip_build: {skip_build}")
    print(f"  skip_push: {skip_push}")
    print()

    dockerfile_path = Path(dockerfile)
    if not dockerfile_path.is_absolute():
        dockerfile_path = Path.cwd() / dockerfile_path

    if not dockerfile_path.exists():
        rich_print(f"[red]Error: Dockerfile not found: {dockerfile_path}[/red]")
        raise typer.Exit(1)

    local_image_tag = "runzi-build:dev" if dev else "runzi-build:latest"

    try:
        if skip_build:
            print(f"Skipping build (using existing {local_image_tag})")
            git_hash = get_git_hash(runzi_gitref)
        else:
            git_hash = build_docker_image(
                str(dockerfile_path),
                python_version,
                fatjar_tag,
                runzi_gitref,
                oq_version,
                install_converter,
                dev,
            )

        if not skip_push:
            ecr_login(region, aws_account_id)
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
            image_uri, image_digest = local_image_tag, "sha256:skipped"

        print()
        stages = [
            ("Build", not skip_build),
            (f"Push image to ECR (:{EXPERIMENTAL_TAG})", not skip_push),
        ]
        completed = [name for name, done in stages if done]
        rich_print(f"[bold green]Completed {', '.join(completed)}![/bold green]")
        print(f"Image: {local_image_tag if dev else image_uri}")
        if not dev:
            print(f"Image digest: {image_digest}")
            rich_print(
                "[yellow]Experimental submissions now resolve this image. "
                "Run `runzi utils promote` to publish it to prod.[/yellow]"
            )
        print()

    except Exception as e:
        rich_print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def promote(
    source: str = typer.Option(
        EXPERIMENTAL_TAG,
        help="Source tag to promote to :prod — the current :experimental image, or a specific "
        "runzi-<hash>... version tag.",
    ),
    region: str = typer.Option("us-east-1", envvar="AWS_REGION", help="AWS region"),
    ecr_repo: str = typer.Option("nzshm22/runzi", envvar="ECR_REPO", help="ECR repository"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt"),
):
    """Promote an already-published image to :prod — changing the shared prod job definition's image.

    This is the only command that touches the prod surface. It moves the :prod tag onto an existing
    image manifest in ECR (no rebuild); the Terraform-owned prod job definition tracks :prod, so the
    promoted image goes live for default submissions on their next run.
    """
    rich_print("[bold]runzi image promotion[/bold]")
    print(f"  ecr_repo: {ecr_repo}")
    print(f"  source tag: {source}")
    print(f"  target tag: {PROD_TAG}")
    print()

    if not yes:
        typer.confirm(
            f"Promote ':{source}' to ':{PROD_TAG}' in {ecr_repo}? "
            f"This changes the image every default (prod) submission runs.",
            abort=True,
        )

    try:
        promoted_digest = retag_image(ecr_repo, region, source, PROD_TAG)
        rich_print(f"[bold green]Promoted :{source} -> :{PROD_TAG}[/bold green]")
        print(f"Prod now resolves to: {promoted_digest}")
        print()
    except Exception as e:
        rich_print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from e


if __name__ == "__main__":
    app()
