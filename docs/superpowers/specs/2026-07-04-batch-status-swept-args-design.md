# Design: identify Batch jobs by swept argument (#335)

**Status:** approved (brainstorming)
**Date:** 2026-07-04
**Issue:** [#335](https://github.com/GNS-Science/nzshm-runzi/issues/335) — "identify batch jobs"
**Builds on:** [#332](https://github.com/GNS-Science/nzshm-runzi/pull/332) (read-only `runzi batch status`)

## Problem

`runzi batch status <GENERAL_TASK_ID>` lists a general task's AWS Batch jobs with
status, duration, and creation time. When a general task sweeps arguments it fans out
into many jobs that are otherwise indistinguishable in the table — the user cannot tell
*which swept-argument combination* each job ran. This design adds that information.

## Goal

For each listed Batch job, show the swept-argument values that job ran with, so a
federated Cognito user (who has no AWS console access) can identify jobs at a glance.

## Approach

Decode each job's **own** encoded config (the config that was shipped to that job's
container at submit time), rather than reconstructing it from toshi or re-encoding it at
submit time.

### Why this approach

Three options were considered:

- **A — Reconstruct from toshi `argument_lists`.** One toshi GraphQL read of the general
  task, then replay `itertools.product(...)` and index by `task_count`. Light, and swept
  keys are directly known (values with length > 1). Rejected because it adds a toshi
  dependency to an otherwise AWS-only command and is a *reconstruction* — if
  `ArgSweeper`'s enumeration ever changes, the labels silently drift from what the jobs
  actually ran.
- **B — Encode swept args into the job name/tags at submit time.** Keeps the query
  AWS-only, but is a submit-side change, is length-limited (Batch job names cap out), and
  is forward-only (won't help already-submitted jobs). Weakest option.
- **C — Decode each job's own encoded config (chosen).** Self-contained in AWS Batch (no
  toshi), **authoritative** (it is literally what the job ran, not a replay), and reuses
  existing code (`decompress_config`). `batch:DescribeJobs` is already granted to the
  `runzi_batch` access tier (per #332).

### Data flow

1. `jobs_for_general_task()` returns the `JobSummary` list (status + timestamps) via the
   existing `list_jobs` job-name-prefix filter — **unchanged**.
2. New step: take those `jobId`s and call `describe_jobs`, batched in groups of **≤100**
   (the AWS `describe_jobs` limit). From each job's `container.environment`, read the
   `TASK_CONFIG_JSON_QUOTED` variable, pass it through the existing
   `decompress_config()` (`runzi/aws/aws.py:194`), `json.loads` the result, and read the
   `task_args` dict (the structure is produced by `get_task_config`:
   `{task_args, task_runtime_args, model_type}`).
3. Compute the **swept keys** by diffing `task_args` across the decoded jobs: any key
   whose value is not identical across all decoded jobs becomes a column. Diff
   `task_args` **only** — never `task_runtime_args` (its `java_gateway_port` varies per
   task but is not user-facing). Sort the resulting keys alphabetically for stable output.

Each job's `task_args` is the prototype with only its swept combination overridden, so the
keys that differ across jobs are exactly the swept ones. Showing all `task_args` keys
would produce dozens of unusable columns; showing only the varying ones is precisely the
disambiguation the issue asks for.

## Display

Table columns become:

```
Job ID · Status · Duration · Created · <swept-key-1> · <swept-key-2> · …
```

- The **Job Name** column is dropped (its encoded `general_task_id` token prefix is
  identical for every row of one general task, and the readable `task_count` tail is
  redundant next to Job ID + swept columns).
- One column **per swept key**, sorted alphabetically.
- Cell value is `str(value)` of that job's swept-arg value. Long/complex values (e.g.
  lists) render via `str()`; no truncation in v1 unless it proves ugly in practice.
- Status colouring, duration, created, and the count-by-status summary line are unchanged.

Example:

```
Job ID     Status     Duration  Created              rupture_set  deformation_model
1a2b-...   SUCCEEDED  0:12:03   2026-07-04 09:00:01  A            geologic
3c4d-...   RUNNING    0:03:11   2026-07-04 09:00:02  A            geodetic
5e6f-...   FAILED     0:00:44   2026-07-04 09:00:03  B            geologic
```

## Error handling / edge cases

- **`describe_jobs` AccessDenied** → same treatment as the existing `list_jobs` denial
  path, with a message naming `batch:DescribeJobs`. (Safety net; the tier already grants
  it.)
- **A job whose config cannot be decoded** (missing env var, decompress/JSON error) →
  that job's swept cells render blank; no crash. Other jobs are unaffected.
- **Only one job survives, or no key varies** → no swept columns appear; the base table
  (today's behaviour) is shown. One job means there is nothing to disambiguate.
- **Retention/inference caveat** — "swept" is inferred from what varies among *visible*
  jobs. Because Batch retains terminal jobs only ~24h, if every job of a given slice has
  aged out, a swept key that is constant across the survivors will not get a column. This
  is documented alongside the existing retention caveat in `--help` and
  `docs/usage/aws_batch.md`. Authoritative labelling regardless of retention would require
  the toshi reconstruction (option A), noted as a possible future enhancement.

## Components / boundaries

- **`runzi/aws/batch_query.py`** — pure, testable logic:
  - a function that, given job IDs and a session, calls `describe_jobs` (batched ≤100),
    extracts + decodes each job's `task_args`, and returns a `{jobId: task_args_dict}`
    mapping (jobs that fail to decode are absent or map to `None`).
  - a function that, given the decoded `task_args` mapping, returns the sorted list of
    swept (varying) keys.
- **`runzi/cli/batch_cli.py`** — presentation only: calls the query helpers, drops the Job
  Name column, renders one column per swept key, fills per-row values (blank when a job's
  config is missing/undecodable), and keeps the existing status colouring and summary.
- **`docs/usage/aws_batch.md`** — document the new columns and the retention/inference
  caveat.

This preserves the existing split (logic in `batch_query`, Rich rendering in `batch_cli`)
so the new behaviour is unit-testable without constructing a table.

## Testing

- **`tests/test_batch_query.py`** (extend):
  - `describe_jobs` extraction: mock `describe_jobs` returning a `container.environment`
    with a real `compress_config`-encoded config; assert the decoder returns the expected
    `task_args` dict. Include a batching test (>100 job IDs → multiple `describe_jobs`
    calls).
  - Swept-key diffing: given several decoded `task_args` dicts, assert only the varying
    keys are returned, sorted; assert `task_runtime_args` is never considered; assert
    identical configs → empty list.
  - Decode-failure path: a job with a missing/garbage env var yields no entry (or `None`)
    rather than raising.
- **`tests/test_batch_cli.py`** (extend):
  - Table has a column per swept key with correct per-row values; the Job Name column is
    gone.
  - No-variation case → no swept columns.
  - `describe_jobs` AccessDenied → friendly message + exit 1.

## Out of scope

- Terminate / log-fetching (still deferred from #332).
- Toshi-based authoritative labelling (option A) — possible future enhancement.
- Value truncation/formatting beyond `str()`.
