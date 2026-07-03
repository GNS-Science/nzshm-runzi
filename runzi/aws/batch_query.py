"""Read-only AWS Batch inspection for federated Cognito users who have no console access (issue #326).

The only linkage from an AWS Batch job back to a runzi general task is a token encoded into the
Batch **job name** at submit time (``batch_job_name``). AWS Batch ``list_jobs`` can filter by queue +
job-name prefix, so this token makes a general task's jobs discoverable without ``describe_jobs`` and
without arbitrary tags (which ``list_jobs`` cannot filter on).
"""

import time
from typing import TYPE_CHECKING, Any

from runzi.arguments import DEFAULT_JOB_QUEUE, EC2_JOB_QUEUE
from runzi.aws.session import get_session

if TYPE_CHECKING:
    import boto3

# Mirror the batch client construction in runzi/job_runner.py:run_jobs().
_BATCH_REGION = 'us-east-1'
_BATCH_ENDPOINT = 'https://batch.us-east-1.amazonaws.com'


def general_task_id_token(gt_id: str) -> str:
    """Return a Batch-job-name-safe token for a toshi general_task_id.

    Batch job names allow ``[A-Za-z0-9_-]`` only. A toshi id is base64 of ``GeneralTask:<int>``, so it
    can contain ``+``, ``/`` and ``=`` padding. We map both ``+`` and ``/`` to ``_`` (deliberately not
    ``-``) and strip ``=`` padding, so the token contains no ``-``. That leaves ``-`` free to act as an
    unambiguous delimiter in ``batch_job_name`` — a ``{token}-*`` prefix filter can then never
    false-match a different general task's job name.
    """
    return gt_id.replace('+', '_').replace('/', '_').replace('=', '')


def batch_job_name(gt_id: str | None, base: str, task_count: int) -> str:
    """Compose the Batch job name, encoding the general_task_id as a discoverable prefix.

    Shared by the submitter (``build_tasks``) and the query side so both agree on the format. This is a
    naming contract: ``jobs_for_general_task`` filters on the ``{token}-`` prefix, so any future change
    to job naming must preserve it. When ``gt_id`` is ``None`` (e.g. non-API runs) we fall back to the
    legacy ``{base}-{task_count}`` form and the job is simply not discoverable by general task.
    """
    if gt_id is None:
        return f'{base}-{task_count}'
    return f'{general_task_id_token(gt_id)}-{base}-{task_count}'


def job_duration(summary: dict[str, Any], now_ms: int | None = None) -> str:
    """Human-readable ``H:MM:SS`` run duration from a Batch JobSummary's epoch-millis timestamps.

    A running job (started, not stopped) counts up to ``now``; a terminal job uses ``stoppedAt``; a job
    that has not started yet has no meaningful duration (``-``).
    """
    started = summary.get('startedAt')
    if started is None:
        return '-'
    stopped = summary.get('stoppedAt')
    if stopped is None:
        stopped = now_ms if now_ms is not None else int(time.time() * 1000)
    seconds = max(0, (stopped - started) // 1000)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f'{hours}:{minutes:02d}:{secs:02d}'


def jobs_for_general_task(
    gt_id: str,
    session: 'boto3.Session | None' = None,
    queues: tuple[str, ...] = (DEFAULT_JOB_QUEUE, EC2_JOB_QUEUE),
) -> list[dict[str, Any]]:
    """Return the Batch JobSummary dicts for a general task, across all runzi queues.

    Filters ``list_jobs`` by the ``{token}-`` job-name prefix. A JOB_NAME filter makes ``list_jobs``
    return jobs of every status (not just RUNNING), and JobSummary already carries status plus the
    created/started/stopped timestamps, so no ``describe_jobs`` call is needed for a status view.
    Results are merged across queues and sorted oldest-first by ``createdAt``.
    """
    client = (session or get_session()).client(
        service_name='batch', region_name=_BATCH_REGION, endpoint_url=_BATCH_ENDPOINT
    )
    name_filter = [{'name': 'JOB_NAME', 'values': [f'{general_task_id_token(gt_id)}-*']}]
    paginator = client.get_paginator('list_jobs')

    jobs: list[dict[str, Any]] = []
    for queue in queues:
        for page in paginator.paginate(jobQueue=queue, filters=name_filter):
            jobs.extend(page.get('jobSummaryList', []))
    jobs.sort(key=lambda job: job.get('createdAt', 0))
    return jobs
