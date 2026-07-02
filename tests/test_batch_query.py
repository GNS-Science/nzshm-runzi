"""Tests for runzi.aws.batch_query — the read-only AWS Batch inspection primitives (issue #326)."""

import re

from runzi.arguments import DEFAULT_JOB_QUEUE, EC2_JOB_QUEUE
from runzi.aws.batch_query import (
    batch_job_name,
    general_task_id_token,
    job_duration,
    jobs_for_general_task,
)

# Batch job names must match this (letters/numbers/underscore/hyphen, start alphanumeric, <=128).
JOB_NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$')


class TestGeneralTaskIdToken:
    def test_is_deterministic(self):
        gt_id = 'R2VuZXJhbFRhc2s6MTAxMjI1'
        assert general_task_id_token(gt_id) == general_task_id_token(gt_id)

    def test_real_gt_id_is_job_name_safe(self):
        # A real toshi id (base64 of "GeneralTask:<int>") is already safe and passes through unchanged.
        assert general_task_id_token('R2VuZXJhbFRhc2s6MTAxMjI1') == 'R2VuZXJhbFRhc2s6MTAxMjI1'

    def test_maps_base64_specials_and_strips_padding(self):
        # '+' and '/' both map to '_' (so the token contains no '-'); '=' padding is stripped.
        assert general_task_id_token('AB+/CD==') == 'AB__CD'

    def test_token_never_contains_a_hyphen(self):
        # The '-' is reserved as the job-name delimiter, so it must never appear inside the token.
        assert '-' not in general_task_id_token('AB+/CD==')


class TestBatchJobName:
    def test_encodes_token_prefix(self):
        gt_id = 'R2VuZXJhbFRhc2s6MTAxMjI1'
        assert batch_job_name(gt_id, 'OpenquakeHazard', 3) == f'{gt_id}-OpenquakeHazard-3'

    def test_none_gt_id_falls_back_to_legacy_format(self):
        assert batch_job_name(None, 'OpenquakeHazard', 3) == 'OpenquakeHazard-3'

    def test_result_is_a_valid_batch_job_name(self):
        assert JOB_NAME_RE.match(batch_job_name('AB+/CD==', 'OpenquakeHazard', 12))

    def test_delimiter_is_unambiguous(self):
        # token has no '-', so splitting on the first '-' recovers the token exactly.
        name = batch_job_name('AB+/CD==', 'Base', 1)
        assert name.split('-', 1)[0] == general_task_id_token('AB+/CD==')


class TestJobDuration:
    def test_completed_job_is_stopped_minus_started(self):
        summary = {'createdAt': 0, 'startedAt': 1_000_000, 'stoppedAt': 1_000_000 + 3_661_000}
        assert job_duration(summary) == '1:01:01'

    def test_running_job_is_now_minus_started(self):
        summary = {'createdAt': 0, 'startedAt': 10_000}
        assert job_duration(summary, now_ms=10_000 + 62_000) == '0:01:02'

    def test_not_yet_started_job_has_no_duration(self):
        assert job_duration({'createdAt': 0}) == '-'


class _FakeBatchClient:
    """Records list_jobs paginate calls per queue and returns canned jobSummaryList pages."""

    def __init__(self, pages_by_queue):
        self._pages_by_queue = pages_by_queue
        self.paginate_calls = []

    def get_paginator(self, name):
        assert name == 'list_jobs'
        return self

    def paginate(self, **kwargs):
        self.paginate_calls.append(kwargs)
        yield from self._pages_by_queue.get(kwargs['jobQueue'], [])


class _FakeSession:
    def __init__(self, client):
        self._client = client

    def client(self, service_name, **kwargs):
        assert service_name == 'batch'
        return self._client


class TestJobsForGeneralTask:
    GT_ID = 'R2VuZXJhbFRhc2s6MTAxMjI1'

    def _client(self):
        return _FakeBatchClient(
            {
                DEFAULT_JOB_QUEUE: [{'jobSummaryList': [{'jobId': 'a', 'createdAt': 200}]}],
                EC2_JOB_QUEUE: [{'jobSummaryList': [{'jobId': 'b', 'createdAt': 100}]}],
            }
        )

    def test_queries_both_queues_with_job_name_prefix_filter(self):
        client = self._client()
        jobs_for_general_task(self.GT_ID, session=_FakeSession(client))

        queried_queues = {call['jobQueue'] for call in client.paginate_calls}
        assert queried_queues == {DEFAULT_JOB_QUEUE, EC2_JOB_QUEUE}
        for call in client.paginate_calls:
            assert call['filters'] == [{'name': 'JOB_NAME', 'values': [f'{self.GT_ID}-*']}]

    def test_merges_results_sorted_by_created_at(self):
        jobs = jobs_for_general_task(self.GT_ID, session=_FakeSession(self._client()))
        assert [j['jobId'] for j in jobs] == ['b', 'a']  # createdAt 100 before 200
