"""Tests for runzi.aws.batch_query — the read-only AWS Batch inspection primitives (issues #326, #337)."""

import json
import re
import urllib.parse

import pytest

from runzi.arguments import DEFAULT_JOB_QUEUE, EC2_JOB_QUEUE
from runzi.aws.aws import compress_config
from runzi.aws.batch_query import (
    JobNotFound,
    LogStreamNotAvailable,
    batch_job_name,
    general_task_id_token,
    job_duration,
    job_log_events,
    jobs_for_general_task,
    swept_arg_keys,
    task_args_by_job_id,
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


def _job_with_config(job_id, task_args):
    config = {
        'task_args': task_args,
        'task_runtime_args': {'task_count': 1},
        'model_type': 10,
    }
    encoded = compress_config(json.dumps(config))
    return {
        'jobId': job_id,
        'container': {'environment': [{'name': 'TASK_CONFIG_JSON_QUOTED', 'value': encoded}]},
    }


def _job_with_quoted_config(job_id, task_args):
    """Build a fake job whose TASK_CONFIG_JSON_QUOTED was written with the URL-quoted (non-compressed) form."""
    config = {
        'task_args': task_args,
        'task_runtime_args': {'task_count': 1},
        'model_type': 10,
    }
    encoded = urllib.parse.quote(json.dumps(config))
    return {
        'jobId': job_id,
        'container': {'environment': [{'name': 'TASK_CONFIG_JSON_QUOTED', 'value': encoded}]},
    }


class _FakeDescribeClient:
    """Records describe_jobs calls and returns canned job detail by id."""

    def __init__(self, jobs_by_id):
        self._jobs_by_id = jobs_by_id
        self.describe_calls = []

    def describe_jobs(self, jobs):
        self.describe_calls.append(list(jobs))
        return {'jobs': [self._jobs_by_id[j] for j in jobs if j in self._jobs_by_id]}


class TestTaskArgsByJobId:
    def test_decodes_task_args_for_each_job(self):
        client = _FakeDescribeClient(
            {
                'a': _job_with_config('a', {'rupture_set': 'A', 'model_id': 'X'}),
                'b': _job_with_config('b', {'rupture_set': 'B', 'model_id': 'X'}),
            }
        )
        result = task_args_by_job_id(['a', 'b'], session=_FakeSession(client))
        assert result == {
            'a': {'rupture_set': 'A', 'model_id': 'X'},
            'b': {'rupture_set': 'B', 'model_id': 'X'},
        }

    def test_batches_describe_jobs_in_chunks_of_100(self):
        ids = [str(n) for n in range(150)]
        client = _FakeDescribeClient({i: _job_with_config(i, {'k': i}) for i in ids})
        task_args_by_job_id(ids, session=_FakeSession(client))
        assert [len(call) for call in client.describe_calls] == [100, 50]

    def test_omits_jobs_with_no_decodable_config(self):
        client = _FakeDescribeClient(
            {
                'a': _job_with_config('a', {'rupture_set': 'A'}),
                'b': {'jobId': 'b', 'container': {'environment': []}},  # no TASK_CONFIG_JSON_QUOTED
                'c': {
                    'jobId': 'c',
                    'container': {'environment': [{'name': 'TASK_CONFIG_JSON_QUOTED', 'value': 'garbage'}]},
                },
            }
        )
        result = task_args_by_job_id(['a', 'b', 'c'], session=_FakeSession(client))
        assert result == {'a': {'rupture_set': 'A'}}

    def test_decodes_url_quoted_config(self):
        """Jobs written with the URL-quoted (non-compressed) form also decode correctly."""
        client = _FakeDescribeClient(
            {
                'a': _job_with_quoted_config('a', {'rupture_set': 'A', 'model_id': 'X'}),
                'b': _job_with_quoted_config('b', {'rupture_set': 'B', 'model_id': 'X'}),
            }
        )
        result = task_args_by_job_id(['a', 'b'], session=_FakeSession(client))
        assert result == {
            'a': {'rupture_set': 'A', 'model_id': 'X'},
            'b': {'rupture_set': 'B', 'model_id': 'X'},
        }


class TestSweptArgKeys:
    def test_returns_only_varying_keys_sorted(self):
        by_job = {
            'a': {'rupture_set': 'A', 'deformation_model': 'geologic', 'model_id': 'X'},
            'b': {'rupture_set': 'A', 'deformation_model': 'geodetic', 'model_id': 'X'},
            'c': {'rupture_set': 'B', 'deformation_model': 'geologic', 'model_id': 'X'},
        }
        assert swept_arg_keys(by_job) == ['deformation_model', 'rupture_set']

    def test_identical_configs_yield_no_keys(self):
        by_job = {'a': {'rupture_set': 'A'}, 'b': {'rupture_set': 'A'}}
        assert swept_arg_keys(by_job) == []

    def test_fewer_than_two_jobs_yields_no_keys(self):
        assert swept_arg_keys({'a': {'rupture_set': 'A'}}) == []
        assert swept_arg_keys({}) == []

    def test_handles_list_valued_args(self):
        by_job = {
            'a': {'vs30s': [200, 300], 'rupture_set': 'A'},
            'b': {'vs30s': [400, 500], 'rupture_set': 'A'},
        }
        assert swept_arg_keys(by_job) == ['vs30s']

    def test_handles_dict_valued_args(self):
        by_job = {
            'a': {'site_params': {'vs30': 200, 'z1pt0': 0.5}},
            'b': {'site_params': {'vs30': 400, 'z1pt0': 0.5}},
        }
        assert swept_arg_keys(by_job) == ['site_params']


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
