# Batch Log Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `runzi batch log <JOB_ID>` that fetches one AWS Batch job's CloudWatch log stream and writes it to `<JOB_ID>.log` in the current directory.

**Architecture:** A new generator `job_log_events` in `runzi/aws/batch_query.py` resolves the job's CloudWatch log group + stream via `describe_jobs`, then pages `get_log_events` to yield log lines. A new Typer `log` command in `runzi/cli/batch_cli.py` materialises those lines to `<JOB_ID>.log` and prints a one-line confirmation, reusing the existing access-denied handling. A terraform change grants the `toshi-runzi-batch` IAM tier `logs:GetLogEvents`.

**Tech Stack:** Python 3.11, Typer, boto3 (AWS Batch + CloudWatch Logs), pytest, Terraform.

## Global Constraints

- Python 3.11 only (`>=3.11,<3.12`).
- Line length 120; single quotes (Black `skip-string-normalization`); Google-style docstrings.
- Use `TYPE_CHECKING` guard for type-hint-only imports (e.g. `boto3`).
- CloudWatch Batch logs live in log group `/aws/batch/job` (our job defs set no custom `logConfiguration`); region is `us-east-1` (mirror `_BATCH_REGION` in `batch_query.py`).
- The query layer is tested with hand-written fake clients/sessions (no mock library); CLI is tested with `typer.testing.CliRunner` + `patch.object`.
- Do not run `git commit` steps if the user has said not to; otherwise commit per task as written.

---

### Task 1: `job_log_events` query function

**Files:**
- Modify: `runzi/aws/batch_query.py` (add exceptions + `job_log_events` + helpers)
- Test: `tests/test_batch_query.py`

**Interfaces:**
- Consumes: existing `get_session`, `_BATCH_REGION`, `_BATCH_ENDPOINT` in `batch_query.py`.
- Produces:
  - `class JobNotFound(Exception)` — no job for the id.
  - `class LogStreamNotAvailable(Exception)` — job exists but has no log stream yet.
  - `def job_log_events(job_id: str, session: 'boto3.Session | None' = None) -> Iterator[str]` — yields log message lines; raises the two exceptions above (lazily, on first iteration) and may raise `botocore.exceptions.ClientError`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_batch_query.py`:

```python
import pytest

from runzi.aws.batch_query import (
    JobNotFound,
    LogStreamNotAvailable,
    job_log_events,
)


def _job_with_stream(job_id, stream='oq/default/abc', log_group=None):
    container = {'logStreamName': stream}
    if log_group is not None:
        container['logConfiguration'] = {'options': {'awslogs-group': log_group}}
    return {'jobId': job_id, 'container': container}


class _FakeLogsClient:
    """Returns canned get_log_events pages in order; records the kwargs of each call."""

    def __init__(self, pages):
        self._pages = pages
        self.calls = []

    def get_log_events(self, **kwargs):
        page = self._pages[len(self.calls)]
        self.calls.append(kwargs)
        return page


class _FakeLogSession:
    def __init__(self, batch_client, logs_client=None):
        self._batch = batch_client
        self._logs = logs_client

    def client(self, service_name, **kwargs):
        if service_name == 'batch':
            return self._batch
        if service_name == 'logs':
            return self._logs
        raise AssertionError(service_name)


class TestJobLogEvents:
    def test_yields_messages_across_paginated_pages(self):
        batch = _FakeDescribeClient({'j1': _job_with_stream('j1')})
        logs = _FakeLogsClient(
            [
                {'events': [{'message': 'line1'}, {'message': 'line2'}], 'nextForwardToken': 't1'},
                {'events': [{'message': 'line3'}], 'nextForwardToken': 't2'},
                {'events': [], 'nextForwardToken': 't2'},  # token unchanged -> stop
            ]
        )
        lines = list(job_log_events('j1', session=_FakeLogSession(batch, logs)))
        assert lines == ['line1', 'line2', 'line3']

    def test_first_call_has_no_next_token_then_pages_with_token(self):
        batch = _FakeDescribeClient({'j1': _job_with_stream('j1')})
        logs = _FakeLogsClient(
            [
                {'events': [{'message': 'a'}], 'nextForwardToken': 't1'},
                {'events': [], 'nextForwardToken': 't1'},
            ]
        )
        list(job_log_events('j1', session=_FakeLogSession(batch, logs)))
        assert 'nextToken' not in logs.calls[0]
        assert logs.calls[1]['nextToken'] == 't1'

    def test_defaults_to_aws_batch_job_log_group(self):
        batch = _FakeDescribeClient({'j1': _job_with_stream('j1', stream='s')})
        logs = _FakeLogsClient([{'events': [], 'nextForwardToken': 't0'}])
        list(job_log_events('j1', session=_FakeLogSession(batch, logs)))
        assert logs.calls[0]['logGroupName'] == '/aws/batch/job'
        assert logs.calls[0]['logStreamName'] == 's'
        assert logs.calls[0]['startFromHead'] is True

    def test_uses_custom_log_group_from_job_config(self):
        batch = _FakeDescribeClient({'j1': _job_with_stream('j1', log_group='/custom/group')})
        logs = _FakeLogsClient([{'events': [], 'nextForwardToken': 't0'}])
        list(job_log_events('j1', session=_FakeLogSession(batch, logs)))
        assert logs.calls[0]['logGroupName'] == '/custom/group'

    def test_raises_job_not_found_when_describe_returns_nothing(self):
        batch = _FakeDescribeClient({})
        with pytest.raises(JobNotFound):
            list(job_log_events('missing', session=_FakeLogSession(batch)))

    def test_raises_log_stream_not_available_when_job_has_no_stream(self):
        batch = _FakeDescribeClient({'j1': {'jobId': 'j1', 'container': {}}})
        with pytest.raises(LogStreamNotAvailable):
            list(job_log_events('j1', session=_FakeLogSession(batch)))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_batch_query.py::TestJobLogEvents -v`
Expected: FAIL with `ImportError: cannot import name 'JobNotFound'` (and `job_log_events`).

- [ ] **Step 3: Write the implementation**

In `runzi/aws/batch_query.py`, add `Iterator` to the typing import line:

```python
from typing import TYPE_CHECKING, Any, Iterator
```

Then append near the end of the module (after `swept_arg_keys`):

```python
_DEFAULT_LOG_GROUP = '/aws/batch/job'  # our Batch job defs set no custom logConfiguration.


class JobNotFound(Exception):
    """Raised when ``describe_jobs`` returns no job for the requested id."""


class LogStreamNotAvailable(Exception):
    """Raised when a job exists but has no CloudWatch log stream yet (e.g. never started)."""


def _log_group_and_stream(job: dict[str, Any]) -> tuple[str, str] | None:
    """Return ``(log_group, log_stream)`` for a Batch job, or ``None`` if it has no stream yet.

    The stream name comes straight from ``container.logStreamName`` (set once the job starts). The
    group is read from the job's ``awslogs`` driver options, defaulting to ``/aws/batch/job`` — the
    group our job definitions use, since they set no custom ``logConfiguration``.
    """
    container = job.get('container', {})
    stream = container.get('logStreamName')
    if not stream:
        return None
    options = container.get('logConfiguration', {}).get('options', {})
    return options.get('awslogs-group', _DEFAULT_LOG_GROUP), stream


def job_log_events(job_id: str, session: 'boto3.Session | None' = None) -> Iterator[str]:
    """Yield the CloudWatch log lines for a single Batch job (issue #337).

    Resolves the job's log group + stream via ``describe_jobs`` then pages ``get_log_events`` from
    the head of the stream, yielding each event's message. Raises ``JobNotFound`` if the id matches
    no job, or ``LogStreamNotAvailable`` if the job has not produced a log stream yet. Both are raised
    lazily on first iteration (this is a generator).
    """
    session = session or get_session()
    batch = session.client(
        service_name='batch', region_name=_BATCH_REGION, endpoint_url=_BATCH_ENDPOINT
    )
    jobs = batch.describe_jobs(jobs=[job_id]).get('jobs', [])
    if not jobs:
        raise JobNotFound(job_id)
    location = _log_group_and_stream(jobs[0])
    if location is None:
        raise LogStreamNotAvailable(job_id)
    log_group, log_stream = location

    logs = session.client(service_name='logs', region_name=_BATCH_REGION)
    kwargs: dict[str, Any] = {
        'logGroupName': log_group,
        'logStreamName': log_stream,
        'startFromHead': True,
    }
    token: str | None = None
    while True:
        if token is not None:
            kwargs['nextToken'] = token
        response = logs.get_log_events(**kwargs)
        for event in response.get('events', []):
            yield event.get('message', '')
        next_token = response.get('nextForwardToken')
        if next_token is None or next_token == token:
            break
        token = next_token
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_batch_query.py::TestJobLogEvents -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Check lint/types**

Run: `ruff check runzi/aws/batch_query.py tests/test_batch_query.py && mypy runzi/aws/batch_query.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add runzi/aws/batch_query.py tests/test_batch_query.py
git commit -m "feat(batch): add job_log_events to fetch a job's CloudWatch log (#337)"
```

---

### Task 2: `runzi batch log` CLI command

**Files:**
- Modify: `runzi/cli/batch_cli.py` (import + new `log` command)
- Test: `tests/test_batch_cli.py`

**Interfaces:**
- Consumes: `job_log_events`, `JobNotFound`, `LogStreamNotAvailable` from Task 1; existing `_exit_on_access_denied`, `console` in `batch_cli.py`.
- Produces: `runzi batch log <JOB_ID>` command writing `<JOB_ID>.log`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_batch_cli.py`:

```python
from pathlib import Path

from runzi.aws.batch_query import JobNotFound, LogStreamNotAvailable


def test_log_writes_file_and_confirmation():
    with runner.isolated_filesystem():
        with patch.object(batch_cli, 'job_log_events', return_value=iter(['line1', 'line2'])):
            result = runner.invoke(runzi_cli.app, ['batch', 'log', 'aaaa-1111'])
        assert result.exit_code == 0
        assert Path('aaaa-1111.log').read_text() == 'line1\nline2\n'
        out = strip_ansi(result.output)
        assert 'aaaa-1111.log' in out
        assert '2' in out  # line count


def test_log_reports_job_not_found():
    with runner.isolated_filesystem():
        with patch.object(batch_cli, 'job_log_events', side_effect=JobNotFound('nope')):
            result = runner.invoke(runzi_cli.app, ['batch', 'log', 'nope'])
        assert result.exit_code == 1
        assert 'no' in strip_ansi(result.output).lower()
        assert not Path('nope.log').exists()


def test_log_reports_no_log_stream_yet():
    with runner.isolated_filesystem():
        with patch.object(batch_cli, 'job_log_events', side_effect=LogStreamNotAvailable('j1')):
            result = runner.invoke(runzi_cli.app, ['batch', 'log', 'j1'])
        assert result.exit_code == 0
        assert 'no log' in strip_ansi(result.output).lower()
        assert not Path('j1.log').exists()


def test_log_handles_access_denied():
    err = ClientError({'Error': {'Code': 'AccessDeniedException', 'Message': 'x'}}, 'GetLogEvents')
    with runner.isolated_filesystem():
        with patch.object(batch_cli, 'job_log_events', side_effect=err):
            result = runner.invoke(runzi_cli.app, ['batch', 'log', 'j1'])
        assert result.exit_code == 1
        assert 'logs:GetLogEvents' in strip_ansi(result.output)
```

Note: `job_log_events` is a generator, so `side_effect=err` (raised when the generator is created via `list(...)`) works because the command calls `list(job_log_events(...))` inside the `try`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_batch_cli.py -k log -v`
Expected: FAIL — the `log` command does not exist (Typer exits non-zero with "No such command").

- [ ] **Step 3: Write the implementation**

In `runzi/cli/batch_cli.py`, update imports:

```python
from pathlib import Path
```

and extend the `batch_query` import:

```python
from runzi.aws.batch_query import (
    JobNotFound,
    LogStreamNotAvailable,
    job_duration,
    job_log_events,
    jobs_for_general_task,
    swept_arg_keys,
    task_args_by_job_id,
)
```

Add the command (after `status`, before `if __name__`):

```python
@app.command()
def log(
    job_id: Annotated[str, typer.Argument(help="the Job ID printed by `runzi batch status`")],
):
    """Fetch a single Batch job's CloudWatch log and write it to ``<JOB_ID>.log`` in the current dir.

    Find the Job ID with `runzi batch status`. AWS Batch keeps terminal jobs (and their logs) for
    only ~24h, so a very old job may no longer have retrievable logs.
    """
    try:
        lines = list(job_log_events(job_id))
    except JobNotFound:
        console.print(
            f"[red]No Batch job found with id {job_id}.[/red] Check the id from `runzi batch "
            "status`; terminal jobs age out of AWS Batch after ~24h."
        )
        raise typer.Exit(code=1) from None
    except LogStreamNotAvailable:
        console.print(
            f"[yellow]Job {job_id} has no log stream yet.[/yellow] It has not started running, so "
            "there are no logs to fetch."
        )
        raise typer.Exit(code=0) from None
    except ClientError as exc:
        _exit_on_access_denied(exc, 'logs:GetLogEvents')
        raise

    path = Path(f"{job_id}.log")
    path.write_text(''.join(f'{line}\n' for line in lines))
    console.print(f"[green]Wrote {len(lines)} line(s) to {path}.[/green]")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_batch_cli.py -k log -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Check lint/types + full batch test files**

Run: `ruff check runzi/cli/batch_cli.py tests/test_batch_cli.py && mypy runzi/cli/batch_cli.py && pytest tests/test_batch_cli.py tests/test_batch_query.py`
Expected: no lint/type errors; all tests pass.

- [ ] **Step 6: Commit**

```bash
git add runzi/cli/batch_cli.py tests/test_batch_cli.py
git commit -m "feat(batch): add \`runzi batch log <JOB_ID>\` command (#337)"
```

---

### Task 3: Grant `logs:GetLogEvents` to the runzi-batch IAM tier

**Files:**
- Modify: `terraform/access/main.tf` (the `toshi-runzi-batch` policy, `aws_iam_policy` with `name = "toshi-runzi-batch-${var.stage}"`, around lines 77-99)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: an additional IAM statement allowing CloudWatch Logs read on the batch log group. **Deferred obligation:** a god-admin must `terraform apply` the access stack for the new `runzi batch log` command to work for scientists; until then it degrades with the access-denied hint from Task 2.

- [ ] **Step 1: Add the logs statement**

In the `policy = jsonencode({ ... Statement = [ ... ] })` of the `toshi-runzi-batch` policy, add a second statement after the existing `BatchSubmit` object:

```hcl
      {
        Sid    = "BatchLogsRead"
        Effect = "Allow"
        Action = [
          "logs:GetLogEvents",
        ]
        Resource = "arn:aws:logs:*:*:log-group:/aws/batch/job:*"
      },
```

The final `Statement` list therefore contains both the `BatchSubmit` and `BatchLogsRead` objects.

- [ ] **Step 2: Verify formatting and that the statement is present**

Run: `cd terraform/access && terraform fmt && cd - >/dev/null && grep -n "BatchLogsRead\|logs:GetLogEvents" terraform/access/main.tf`
Expected: `terraform fmt` reports no changes (or reformats cleanly); grep shows the `BatchLogsRead` Sid and `logs:GetLogEvents` action.

- [ ] **Step 3: Commit**

```bash
git add terraform/access/main.tf
git commit -m "feat(access): grant runzi-batch tier logs:GetLogEvents for batch log (#337)"
```

---

## Post-implementation

- The three commits deliver: the query primitive, the CLI command, and the IAM grant.
- **Deferred deploy obligation:** the `terraform/access` stack must be applied by a god-admin deployer before scientists can use `runzi batch log`. Note this in the PR description.
- Optional manual smoke test (requires an applied policy + real job id):
  `runzi batch status <GT_ID>` to get a Job ID, then `runzi batch log <JOB_ID>` and inspect `<JOB_ID>.log`.
