# Running the container without installing runzi

This page is for users who want to run runzi tasks locally using **only** the
Docker image — without `pip install`-ing runzi itself.

The `runzi --docker` flags (see [Running the container locally](run_locally.md))
do all the right orchestration — pull the image, mount your config/credentials,
forward env vars, map your user ID — but they are only reachable through an
installed runzi. The good news: that orchestration lives in a **single,
dependency-free Python file** (`runzi/cli/docker_wrapper.py`) that you can
download and run directly. runzi itself is already installed *inside* the image,
so the container does the real work; the launcher just assembles the `docker run`.

## Prerequisites

- **Docker** installed and running.
- The **AWS CLI** (used once to log Docker in to ECR when the image is pulled).
- **Python 3.10+** (standard library only — the launcher needs no third-party
  Python packages; `rich` and `python-dotenv` are used if present but are
  optional).
- **`nshm-toshi-client`** for authentication (this is *not* runzi — it is a small,
  standalone package):

    ```console
    pip install nshm-toshi-client
    ```

## One-time authentication

runzi authenticates to the toshi API and to AWS entirely through Cognito. Two
commands from `nshm-toshi-client` produce the credential files the launcher
mounts into the container:

```console
toshi-auth login       # writes ~/.toshi/credentials (JWT for the toshi API)
toshi-auth aws-creds   # writes ~/.aws/credentials under the [toshi] profile (federated AWS creds)
export AWS_PROFILE=toshi
```

- `toshi-auth login` is a terminal username/password flow — no browser needed.
- `toshi-auth aws-creds` federates short-lived AWS credentials from the Cognito
  Identity Pool. These are needed to **pull the image from ECR** and to write to
  an **`s3://` THS database**. If your THS dataset is a **local directory**, you
  do not need `aws-creds` or `AWS_PROFILE` — only `toshi-auth login`.
- The federated AWS credentials are short-lived (about an hour). If a long job
  fails with an AWS credential/expiry error, re-run `toshi-auth aws-creds`.

## Get the launcher

The runzi repository is public, so the launcher can be downloaded with no auth:

```console
curl -fsSL https://raw.githubusercontent.com/GNS-Science/nzshm-runzi/main/runzi/cli/docker_wrapper.py -o runzi-docker
chmod +x runzi-docker
```

## Configure your `.env`

Create a `.env` file in your working directory with the same `NZSHM22_*`
configuration you would use for a normal runzi run (toshi/Cognito URLs and IDs,
THS database locations, etc.). See
[Environment Variables](../environment_variables.md). The launcher loads `.env`
from the current directory automatically. `AWS_PROFILE`, `AWS_REGION`, and the
`NZSHM22_*` values are forwarded into the container.

## Run tasks

Invoke it exactly like `runzi --docker`, but as `./runzi-docker` (the `--docker`
prefix is unnecessary — this script *is* the docker launcher):

```console
./runzi-docker hazard oq-hazard config.json
./runzi-docker inversion crustal config.json
```

The launcher pulls the image from ECR on first use (logging in with your
`toshi` AWS profile), mounts the config file's parent directory at
`/INPUT_FILES`, mounts your `~/.aws` and `~/.toshi` credentials, forwards the
allow-listed env vars, and runs the container as your host user ID.

### Meta-flags

The same `--docker-*` meta-flags are available (minus the redundant `--docker`):

| Flag | Purpose |
|---|---|
| `--docker-shell` | Drop into an interactive bash session inside the container |
| `--docker-image TEXT` | Override the image tag or full ECR/registry URI |
| `--docker-dry-run` | Print the `docker run` command without executing it |

```console
./runzi-docker --docker-shell
./runzi-docker --docker-dry-run hazard oq-hazard config.json
./runzi-docker --docker-image 461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi:latest hazard oq-hazard config.json
```

`--docker-dry-run` is the quickest way to see exactly what will run and confirm
your mounts and env are correct before pulling or launching anything.

### Config files that reference other files

As with `runzi --docker`, config files may only reference other files via
**relative paths** to the same directory or a subdirectory — only the config's
parent directory is mounted at `/INPUT_FILES`.
