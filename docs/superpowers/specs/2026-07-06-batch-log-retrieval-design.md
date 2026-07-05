# Design: `runzi batch log <JOB_ID>` — retrieve batch logs (issue #337)

## Problem

Users of the AWS Batch computation want to inspect the logs of an individual job.
Federated Cognito users have no AWS console access, so — as with `runzi batch status`
(issue #326) — they need a CLI path to the CloudWatch logs a Batch job produces. Users
find the Job ID from `runzi batch status`; the command dumps that job's log to a local
file named `<JOB_ID>.log`.

## Goal

Add `runzi batch log <JOB_ID>` that fetches one Batch job's CloudWatch log stream and
writes it to `<JOB_ID>.log` in the current directory.

## Background

- Our Batch job definitions (`terraform/batch/main.tf`) set **no** custom
  `logConfiguration`, so Batch uses the default `awslogs` driver: log group
  `/aws/batch/job`, stream name available from `describe_jobs` as
  `container.logStreamName`.
- The `toshi-runzi-batch` IAM tier (`terraform/access/main.tf`) currently grants
  `batch:DescribeJobs` / `batch:ListJobs` etc. but **no** CloudWatch Logs read
  permission. Fetching logs requires adding `logs:GetLogEvents`.

## Design

### 1. Query function — `runzi/aws/batch_query.py`

```python
def job_log_events(job_id: str, session=None) -> Iterator[str]
```

- `describe_jobs(jobs=[job_id])` → the single job dict.
  - No job returned → raise a small sentinel the CLI turns into a "job not found"
    message (exit 1).
  - `container.logStreamName` absent (job still RUNNABLE/queued, never started) →
    signal "no log stream yet" so the CLI can report it cleanly.
  - Log group from `container.logConfiguration.options['awslogs-group']`, defaulting
    to `/aws/batch/job` (matches our job defs).
- CloudWatch Logs client built with the same region/session pattern as the batch
  client (`us-east-1`). `get_log_events(logGroupName, logStreamName,
  startFromHead=True)`, looping on `nextForwardToken` until the token stops advancing
  (documented end-of-stream signal). Yield each event's `message`.

### 2. CLI command — `runzi/cli/batch_cli.py`

```python
@app.command()
def log(job_id: Annotated[str, typer.Argument(help=...)]):
```

- Calls `job_log_events`, writes each message as a line to `<job_id>.log` in the cwd
  (overwrites if present).
- On success prints one confirmation line: file path + number of lines written.
- Wraps `ClientError` via the existing `_exit_on_access_denied` helper, extended to
  cover `logs:GetLogEvents` (tells the user their tier lacks log read — relevant until
  the IAM change below is applied).
- Friendly, non-crashing messages for "job not found" (exit 1) and "no log stream yet"
  (clean message, the job simply has not produced logs).

### 3. IAM — `terraform/access/main.tf`

Add a statement to the `toshi-runzi-batch` policy granting `logs:GetLogEvents`, scoped
to the batch log group:

```
Resource = "arn:aws:logs:*:*:log-group:/aws/batch/job:*"
```

**Deferred obligation:** a god-admin must `terraform apply` the access stack before the
command works for scientists. Until then the command degrades gracefully with the
access-denied hint.

### 4. Tests

- `tests/test_batch_query.py`: mock `describe_jobs` + `get_log_events`, covering
  pagination (token loop terminates), the no-log-stream case, and the not-found case.
- `tests/test_batch_cli.py`: file written with expected content, confirmation line,
  access-denied handling, job-not-found handling.

## Non-goals (YAGNI)

- No `--output` path flag (issue fixes the filename as `<JOB_ID>.log`).
- No tail/follow mode.
- No multi-job fetch.
- No streaming log content to stdout.
