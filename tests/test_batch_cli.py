"""Tests for the `runzi batch status` CLI (issue #326)."""

import re
from unittest.mock import patch

from botocore.exceptions import ClientError
from typer.testing import CliRunner

from runzi.cli import batch_cli, runzi_cli

runner = CliRunner(env={"NO_COLOR": "1", "LANG": "en_US.UTF-8", "COLUMNS": "200"})

GT_ID = 'R2VuZXJhbFRhc2s6MTAxMjI1'


def strip_ansi(text: str) -> str:
    return re.sub(r'\x1b\[[0-9;]*m', '', text)


SUMMARIES = [
    {
        'jobId': 'aaaa-1111',
        'jobName': f'{GT_ID}-job-1',
        'status': 'SUCCEEDED',
        'createdAt': 1_000_000,
        'startedAt': 1_010_000,
        'stoppedAt': 1_070_000,
    },
    {
        'jobId': 'bbbb-2222',
        'jobName': f'{GT_ID}-job-2',
        'status': 'RUNNING',
        'createdAt': 1_005_000,
        'startedAt': 1_015_000,
    },
]


def test_status_renders_rows_and_status_counts():
    with patch.object(batch_cli, 'jobs_for_general_task', return_value=SUMMARIES) as mock_jobs:
        result = runner.invoke(runzi_cli.app, ['batch', 'status', GT_ID])

    assert result.exit_code == 0
    mock_jobs.assert_called_once_with(GT_ID)
    out = strip_ansi(result.output)
    assert 'aaaa-1111' in out
    assert 'bbbb-2222' in out
    assert 'SUCCEEDED' in out
    assert 'RUNNING' in out


def test_status_reports_when_no_jobs_found():
    with patch.object(batch_cli, 'jobs_for_general_task', return_value=[]):
        result = runner.invoke(runzi_cli.app, ['batch', 'status', GT_ID])

    assert result.exit_code == 0
    assert 'no' in strip_ansi(result.output).lower()


def test_status_handles_access_denied():
    err = ClientError({'Error': {'Code': 'AccessDeniedException', 'Message': 'not authorized'}}, 'ListJobs')
    with patch.object(batch_cli, 'jobs_for_general_task', side_effect=err):
        result = runner.invoke(runzi_cli.app, ['batch', 'status', GT_ID])

    assert result.exit_code == 1
    assert 'batch:ListJobs' in strip_ansi(result.output)
