"""Read-only AWS Batch inspection for federated Cognito users who have no console access (issue #326).

The only linkage from an AWS Batch job back to a runzi general task is a token encoded into the
Batch **job name** at submit time (``batch_job_name``). AWS Batch ``list_jobs`` can filter by queue +
job-name prefix, so this token makes a general task's jobs discoverable without ``describe_jobs`` and
without arbitrary tags (which ``list_jobs`` cannot filter on).
"""

import json
import time
import urllib.parse
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from runzi.arguments import DEFAULT_JOB_QUEUE, EC2_JOB_QUEUE
from runzi.aws.aws import decompress_config
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


_DESCRIBE_JOBS_BATCH = 100  # AWS describe_jobs accepts at most 100 job ids per call.


def _decode_task_args(job: dict[str, Any]) -> dict[str, Any] | None:
    """Decode a job's shipped ``task_args`` from its ``TASK_CONFIG_JSON_QUOTED`` container env var.

    Returns ``None`` if the variable is absent or cannot be decompressed/parsed (e.g. a legacy job),
    so the caller can render a blank rather than crashing the whole table for one bad job.
    """
    environment = job.get('container', {}).get('environment', [])
    encoded = next((e.get('value') for e in environment if e.get('name') == 'TASK_CONFIG_JSON_QUOTED'), None)
    if not encoded:
        return None
    try:
        # Mirror the worker's get_config() decode order: URL-quoted first, compressed second.
        try:
            config = json.loads(urllib.parse.unquote(encoded))
        except (json.JSONDecodeError, ValueError):
            config = json.loads(decompress_config(encoded))
    except Exception:
        return None
    if not isinstance(config, dict):
        return None
    return config.get('task_args')


def task_args_by_job_id(
    job_ids: list[str],
    session: 'boto3.Session | None' = None,
) -> dict[str, dict[str, Any]]:
    """Return ``{job_id: task_args}`` by decoding each job's own shipped config (issue #335).

    Each Batch job carries the exact config it ran in ``TASK_CONFIG_JSON_QUOTED``; this reads it back
    with ``describe_jobs`` (batched in groups of 100, the AWS limit) rather than reconstructing it.
    Jobs whose config is missing or undecodable are omitted from the mapping.
    """
    client = (session or get_session()).client(
        service_name='batch', region_name=_BATCH_REGION, endpoint_url=_BATCH_ENDPOINT
    )
    result: dict[str, dict[str, Any]] = {}
    for start in range(0, len(job_ids), _DESCRIBE_JOBS_BATCH):
        chunk = job_ids[start : start + _DESCRIBE_JOBS_BATCH]
        for job in client.describe_jobs(jobs=chunk).get('jobs', []):
            task_args = _decode_task_args(job)
            if task_args is not None:
                result[job['jobId']] = task_args
    return result


_DESCRIBE_CONTAINER_INSTANCES_BATCH = 100  # ECS describe_container_instances accepts at most 100 per call.
_DESCRIBE_INSTANCES_BATCH = 100  # keep EC2 describe_instances calls modest; well under any page limit.


def _cluster_from_container_instance_arn(arn: str) -> str | None:
    """Return the ECS cluster name embedded in a long-format container-instance ARN, else ``None``.

    ``describe_container_instances`` is cluster-scoped, so we recover the cluster from the ARN itself.
    Long-format ARNs (the AWS default since 2018) are
    ``arn:aws:ecs:<region>:<acct>:container-instance/<cluster>/<id>``; a short-format ARN (no cluster
    segment) returns ``None`` and that instance is simply skipped.
    """
    tail = arn.split(':')[-1]  # 'container-instance/<cluster>/<id>' for long-format ARNs
    parts = tail.split('/')
    if len(parts) != 3 or parts[0] != 'container-instance':
        return None
    return parts[1]


def _container_instance_arn_by_job(batch: Any, job_ids: list[str]) -> dict[str, str]:
    """Return ``{job_id: containerInstanceArn}`` from ``describe_jobs``, skipping jobs without one.

    Only placed EC2 jobs carry a ``containerInstanceArn`` — Fargate and not-yet-placed jobs are
    dropped. ``describe_jobs`` is batched in groups of 100 (the AWS limit), like ``task_args_by_job_id``.
    """
    result: dict[str, str] = {}
    for start in range(0, len(job_ids), _DESCRIBE_JOBS_BATCH):
        chunk = job_ids[start : start + _DESCRIBE_JOBS_BATCH]
        for job in batch.describe_jobs(jobs=chunk).get('jobs', []):
            arn = job.get('container', {}).get('containerInstanceArn')
            if arn:
                result[job['jobId']] = arn
    return result


def _ec2_id_by_container_instance_arn(ecs: Any, ci_arns: set[str]) -> dict[str, str]:
    """Return ``{containerInstanceArn: ec2InstanceId}`` via cluster-scoped ``describe_container_instances``.

    ARNs are grouped by the cluster parsed from each ARN (the call is cluster-scoped) and each cluster's
    ARNs are queried in chunks of 100. Instances whose cluster can't be parsed are skipped.
    """
    arns_by_cluster: dict[str, list[str]] = {}
    for arn in ci_arns:
        cluster = _cluster_from_container_instance_arn(arn)
        if cluster is not None:
            arns_by_cluster.setdefault(cluster, []).append(arn)
    result: dict[str, str] = {}
    for cluster, arns in arns_by_cluster.items():
        for start in range(0, len(arns), _DESCRIBE_CONTAINER_INSTANCES_BATCH):
            chunk = arns[start : start + _DESCRIBE_CONTAINER_INSTANCES_BATCH]
            described = ecs.describe_container_instances(cluster=cluster, containerInstances=chunk)
            for ci in described.get('containerInstances', []):
                ec2_id = ci.get('ec2InstanceId')
                if ec2_id:
                    result[ci['containerInstanceArn']] = ec2_id
    return result


def _type_by_ec2_id(ec2: Any, ec2_ids: set[str]) -> dict[str, str]:
    """Return ``{ec2InstanceId: InstanceType}`` via ``describe_instances``, batched in groups of 100."""
    ids = list(ec2_ids)
    result: dict[str, str] = {}
    for start in range(0, len(ids), _DESCRIBE_INSTANCES_BATCH):
        chunk = ids[start : start + _DESCRIBE_INSTANCES_BATCH]
        described = ec2.describe_instances(InstanceIds=chunk)
        for reservation in described.get('Reservations', []):
            for instance in reservation.get('Instances', []):
                instance_type = instance.get('InstanceType')
                if instance_type:
                    result[instance['InstanceId']] = instance_type
    return result


def instance_type_by_job_id(
    job_ids: list[str],
    session: 'boto3.Session | None' = None,
) -> dict[str, str]:
    """Return ``{job_id: ec2_instance_type}`` for the EC2 instance each Batch job actually ran on (#323).

    Under a ``BEST_FIT_PROGRESSIVE`` / ``["optimal"]`` compute environment, Batch — not the caller —
    picks the instance type, so cost can only be attributed by reading back which instance ran each
    job. The chain is: ``batch.describe_jobs`` → ``container.containerInstanceArn`` (present only for
    placed EC2 jobs) → ECS ``describe_container_instances`` (cluster-scoped) → ``ec2InstanceId`` →
    EC2 ``describe_instances`` → ``InstanceType``. Jobs that are Fargate, not yet placed, or whose
    lookups don't resolve are omitted from the mapping rather than raising.
    """
    session = session or get_session()
    batch = session.client(service_name='batch', region_name=_BATCH_REGION, endpoint_url=_BATCH_ENDPOINT)
    ci_arn_by_job = _container_instance_arn_by_job(batch, job_ids)
    if not ci_arn_by_job:
        return {}

    ecs = session.client(service_name='ecs', region_name=_BATCH_REGION)
    ec2_id_by_ci_arn = _ec2_id_by_container_instance_arn(ecs, set(ci_arn_by_job.values()))
    if not ec2_id_by_ci_arn:
        return {}

    ec2 = session.client(service_name='ec2', region_name=_BATCH_REGION)
    type_by_ec2_id = _type_by_ec2_id(ec2, set(ec2_id_by_ci_arn.values()))

    # Stitch job_id -> instance type, dropping any link that didn't resolve.
    result: dict[str, str] = {}
    for job_id, ci_arn in ci_arn_by_job.items():
        instance_type = type_by_ec2_id.get(ec2_id_by_ci_arn.get(ci_arn, ''))
        if instance_type is not None:
            result[job_id] = instance_type
    return result


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
    batch = session.client(service_name='batch', region_name=_BATCH_REGION, endpoint_url=_BATCH_ENDPOINT)
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
        events = response.get('events', [])
        for event in events:
            yield event.get('message', '')
        next_token = response.get('nextForwardToken')
        if not events or next_token is None or next_token == token:
            break
        token = next_token


def swept_arg_keys(task_args_by_job: dict[str, dict[str, Any]]) -> list[str]:
    """Return the sorted ``task_args`` keys whose value differs across jobs — i.e. the swept ones.

    Each job's ``task_args`` is the prototype with only its swept combination overridden, so the keys
    that vary across jobs are exactly the swept ones. Values are compared via a canonical JSON form so
    list/dict-valued args compare correctly. Fewer than two decoded jobs means nothing to disambiguate.
    """
    configs = list(task_args_by_job.values())
    if len(configs) < 2:
        return []
    all_keys: set[str] = set().union(*(config.keys() for config in configs))
    varying = [
        key
        for key in all_keys
        if len({json.dumps(config.get(key), sort_keys=True, default=str) for config in configs}) > 1
    ]
    return sorted(varying)
