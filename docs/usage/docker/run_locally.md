# Running the docker container locally

Users may want to run the docker container locally so that all dependencies (OpenSHA and OpenQuake) are available. If you are not running jobs locally — only spawning them from your local machine — it is not necessary to run runzi in the container, as the dependencies will be available on the cloud container.

## Using the `--docker` flag (recommended)

The easiest way to run a command inside the container is to add `--docker` to any normal `runzi` invocation:

```console
runzi --docker hazard oq-hazard /path/to/config.json
runzi --docker inversion crustal /path/to/config.json
```

The wrapper automatically:

- Pulls the image from ECR if it is not present locally.
- Mounts the config file's parent directory at `/INPUT_FILES` inside the container (all subdirectories are included, so configs that reference other files via relative paths work without extra flags).
- Mounts your AWS credentials read-only.
- Mounts your local THS dataset directories (from `$NZSHM22_THS_RLZ_DB` and `$NZSHM22_THS_DISAGG_RLZ_DB`) if they are local paths. If they are `s3://` URIs they are forwarded as environment variables instead.
- Runs the container as your host user ID so output files are owned by you, not root.
- Forwards all `NZSHM22_*`, `AWS_PROFILE`, `AWS_REGION`, and `THS_DATASET_AGGR_URI` environment variables from your `.env` file.

### Prerequisites

- Docker installed and running.
- A `.env` file in your working directory (or the relevant env vars exported in your shell) — the same file you use for normal runzi runs.
- AWS credentials at `~/.aws/credentials`.

### Convention for config files that reference other files

When using `--docker`, config files may only reference other files via **relative paths** to the same directory or a subdirectory. For example, if your config lives at `/data/jobs/run1/config.json` and references `../srm.zip`, that reference will not be accessible inside the container. Move `srm.zip` into `/data/jobs/run1/` or a subdirectory.

### Interactive shell

To drop into a bash shell inside the container with all mounts ready (useful for running multiple commands or debugging):

```console
runzi --docker-shell
```

### Available `--docker-*` flags

| Flag | Purpose |
|---|---|
| `--docker` | Route the command through a local Docker container |
| `--docker-image TEXT` | Override the image tag or full ECR URI; implies `--docker` |
| `--docker-shell` | Drop into an interactive bash session; implies `--docker` |
| `--docker-dry-run` | Print the docker command without running it; implies `--docker` |

## Can't install runzi?

If you don't want to install runzi at all, use the **standalone launcher** — a
single dependency-free download that gives you the same `--docker` convenience.
See [Running the container without installing runzi](run_without_install.md).

## Fallback: raw `docker run`

If you cannot install runzi on the host and would rather not use the standalone
launcher, you can run the container directly. Replace `[COMMAND] [SUBCOMMAND] [OPTIONS]` with the runzi command you wish to run (e.g. `hazard oq-hazard /INPUT_FILES/config.json`).

The examples below reference the published `:prod` image; `docker run` pulls it on
first use once you have logged Docker in to ECR (the deploy pipeline publishes
`:prod`, `:experimental`, and immutable version tags — there is no `:latest`):

```console
aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin 461564345538.dkr.ecr.us-east-1.amazonaws.com
```

### With a local THS dataset

```console
docker run --rm --user "$(id -u):$(id -g)" --entrypoint runzi \
  -v <path to input files>:/INPUT_FILES:ro \
  -v $HOME/.aws/credentials:/aws-credentials:ro \
  -v $NZSHM22_THS_RLZ_DB:/THS/HAZARD \
  -v $NZSHM22_THS_DISAGG_RLZ_DB:/THS/DISAGG \
  -e AWS_SHARED_CREDENTIALS_FILE=/aws-credentials \
  -e AWS_PROFILE \
  -e NZSHM22_TOSHI_S3_URL \
  -e NZSHM22_TOSHI_API_URL \
  -e NZSHM22_TOSHI_API_KEY \
  -e NZSHM22_RUNZI_ECR_DIGEST \
  461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi:prod [COMMAND] [SUBCOMMAND] [OPTIONS]
```

### With an S3 THS dataset

Set `NZSHM22_THS_RLZ_DB` and `NZSHM22_THS_DISAGG_RLZ_DB` to `s3://` URIs and omit the `/THS` mounts:

```console
docker run --rm --user "$(id -u):$(id -g)" --entrypoint runzi \
  -v <path to input files>:/INPUT_FILES:ro \
  -v $HOME/.aws/credentials:/aws-credentials:ro \
  -e AWS_SHARED_CREDENTIALS_FILE=/aws-credentials \
  -e NZSHM22_THS_RLZ_DB \
  -e NZSHM22_THS_DISAGG_RLZ_DB \
  -e THS_DATASET_AGGR_URI \
  -e AWS_PROFILE \
  -e NZSHM22_TOSHI_S3_URL \
  -e NZSHM22_TOSHI_API_URL \
  -e NZSHM22_TOSHI_API_KEY \
  -e NZSHM22_RUNZI_ECR_DIGEST \
  461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi:prod [COMMAND] [SUBCOMMAND] [OPTIONS]
```
