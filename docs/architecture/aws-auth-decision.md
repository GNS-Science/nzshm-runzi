# AWS authentication: in-memory Cognito session vs `~/.aws/credentials`

## Decision

**runzi uses an in-memory Cognito → boto3.Session path via `nshm_toshi_client.aws.get_aws_session()`** for its own boto3 clients (AWS Batch, Secrets Manager, S3 report upload). Scientists authenticate once with `toshi-auth login`; runzi performs the Cognito Identity Pool federation on each invocation without writing credentials to disk.

`toshi-auth aws-creds` remains available as a side channel for any future ad-hoc need (debugging, a one-off `aws s3 cp`, future tools that read `~/.aws/credentials`). The two paths coexist on the same `~/.toshi/credentials`.

### THS S3 write exception (pyarrow disk-path)

The THS realization/disagg S3 write — `toshi_hazard_store.store_hazard` → `pyarrow_dataset.py:
fs.S3FileSystem(region=REGION)` — constructs its own filesystem object and **cannot receive
runzi's in-memory boto3.Session**. It resolves credentials via the AWS C++ SDK default chain:
env keys → `AWS_SHARED_CREDENTIALS_FILE` / `~/.aws/credentials` + `AWS_PROFILE` → instance role.

Under `--docker` this means the container must have the Cognito `[toshi]` profile available via
the disk path:

1. `toshi-auth aws-creds` writes STS credentials to `~/.aws/credentials` as the `[toshi]`
   profile on the host.
2. The docker wrapper mounts `~/.aws/credentials` → `/aws-credentials:ro`
   (`docker_wrapper.py:129`).
3. The wrapper sets `-e AWS_SHARED_CREDENTIALS_FILE=/aws-credentials`
   (`docker_wrapper.py:151`) so the C++ SDK reads the mounted file.
4. `AWS_PROFILE=toshi` is forwarded from the host (it is in `_ENV_PASSTHROUGH`), selecting the
   correct profile.

Lines 129 and 151 in `docker_wrapper.py` are therefore **intentionally active** for the THS S3
path. The operator must re-run `toshi-auth aws-creds` whenever the `[toshi]` STS creds expire
(~1h TTL) before running a `--docker` job that writes to S3.

## Two deciding inputs

1. **runzi is the only AWS-touching tool in the current team workflow.** Scientists don't run `aws-cli`, don't open the AWS console for AWS work, and don't touch boto3 directly in notebooks. That eliminates the strongest argument for the disk path (tool consistency / `~/.aws/credentials` as a universal credential source). If `toshi-auth aws-creds` would exist solely to serve runzi, making runzi do the exchange itself is strictly less friction for the same result.
2. **Usage pattern is mixed.** Some scientists iterate all day, some submit and walk away. The in-memory path's silent auto-refresh helps the former and is neutral for the latter; the disk path helps neither and adds steps to both. The in-memory default is strictly better when the usage pattern is unpredictable.

## Background

Both paths use the same Cognito Identity Pool authenticated role and end up with identical STS credentials. The only difference is *delivery mechanism*:

| | Disk path | In-memory path |
|---|---|---|
| **Implementation** | `toshi-auth aws-creds` (a CLI in `nshm-toshi-client`) exchanges Cognito tokens for STS creds and writes them to `~/.aws/credentials` as profile `[toshi]`. boto3/aws-cli pick them up via `AWS_PROFILE=toshi`. | `nshm_toshi_client.aws.get_aws_session()` performs the exchange in-process and returns a `boto3.Session`. runzi calls it via the thin wrapper in `runzi/aws/session.py`. |
| **Auth steps per session** | `toshi-auth login` + `toshi-auth aws-creds` + `export AWS_PROFILE=toshi`. | `toshi-auth login` only. |
| **STS expiry (~1h)** | User re-runs `aws-creds`; gets `ExpiredTokenException` from AWS if they forget. | runzi mints fresh STS creds on every invocation. |
| **Cognito access_token expiry (~1h)** | `aws-creds` fails → user re-runs `toshi-auth login`. | Library refreshes via `refresh_token` (silent). |
| **Docker wrapper** | Would need `~/.aws/credentials` mount + `AWS_SHARED_CREDENTIALS_FILE` env var re-enabled (currently commented out in `runzi/cli/docker_wrapper.py:129,151` as `# TEMP: testing IAM auth`). | Only the existing `~/.toshi` mount is required. |
| **Tool consistency** | One credential source serves all tools (aws-cli, terraform, console federation, notebooks). | runzi-only; other tools still need `aws-creds` if they're ever used. |
| **Credential leakage surface** | World-readable `~/.aws/credentials` is the classic mishap. STS creds expire in 1h so the leakage window is bounded. | `~/.toshi/credentials` holds the refresh_token, which has a much longer lifetime — leakage of *that* file is arguably worse. |
| **Code locality** | Zero runzi code; minimal upstream code (`toshi-auth aws-creds` CLI). | ~37 lines in `runzi/aws/session.py` + ~120 lines in `nshm_toshi_client/aws.py`. |
| **Standard / familiar** | Every AWS user understands `~/.aws/credentials` and `AWS_PROFILE`. | Custom; new scientists need to learn that runzi has a special auth path. |
| **Failure mode visibility** | `aws sts get-caller-identity` is the universal debug command. | Failure messages route through runzi's warning log; less standard to debug. |

## Auto-refresh behaviour by usage pattern

| Pattern | Disk path | In-memory path |
|---|---|---|
| Submit one sweep then walk away | Works. STS lives for the sweep. | Works. |
| Submit, come back 2h later, submit again | STS expired → AWS errors on next submit. User runs `aws-creds`; if access_token *also* expired, `aws-creds` errors and user runs `toshi-auth login`. | Library refreshes access_token via refresh_token (silent). Fresh STS minted. User unaware anything was expired. |
| Iterate all day (submit, edit, submit, edit) | Friction every hour: re-run `aws-creds`, sometimes re-run `login`. | Silent for the lifetime of the refresh_token (~30d in default Cognito config). |
| Long single sweep, submit loop > 1h | Late `submit_job` calls hit `ExpiredTokenException`. | If we acquire the session once at the start of `run_jobs()` and reuse it, same exposure unless we rebuild inside the loop. Currently we don't — *partial* win. A real fix is `botocore.credentials.RefreshableCredentials` wrapping `get_aws_session()`, not done in either path. |

## Followups not blocking this decision

- **Upstream improvement worth filing**: `toshi-auth aws-creds` could call `ToshiCredentialAuth.get_id_token()` to refresh the access_token via the refresh_token before exchanging for STS. That removes the "your access_token also expired, please re-login" half of the disk-path friction and improves `aws-creds` for any non-runzi consumer.
- **Long sweep robustness**: wrap `get_aws_session()` in `botocore.credentials.RefreshableCredentials` so any submit loop that spans the STS expiry window keeps minting fresh creds silently. Only worth doing if real sweeps actually run that long; check submit-loop durations first.

## Files

- `runzi/aws/session.py` — thin wrapper around `nshm_toshi_client.aws.get_aws_session()` with fallback to the default boto3 credential chain on any `CognitoAuthError` or `ImportError`.
- `runzi/cli/docker_wrapper.py:129,151` — disabled `~/.aws/credentials` mount lines, kept commented as a record of the prior direction.
- `nshm_toshi_client.aws` (upstream) — programmatic `get_aws_session()` and the `CognitoAuthError` exception hierarchy that runzi consumes.
