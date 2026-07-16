"""Tests for the `runzi batch` CLI commands: `status` (issue #326) and `log` (issue #337)."""

import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from botocore.exceptions import ClientError
from typer.testing import CliRunner

from runzi.aws.batch_query import JobNotFound, LogStreamNotAvailable
from runzi.cli import batch_cli, runzi_cli

runner = CliRunner(env={"NO_COLOR": "1", "LANG": "en_US.UTF-8", "COLUMNS": "200"})


@contextmanager
def isolated_filesystem():
    """typer's CliRunner dropped isolated_filesystem() in 0.26; reimplement the bit we need."""
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp_dir:
        os.chdir(tmp_dir)
        try:
            yield tmp_dir
        finally:
            os.chdir(cwd)

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
    with patch.object(batch_cli, 'jobs_for_general_task', return_value=SUMMARIES) as mock_jobs, patch.object(
        batch_cli, 'task_args_by_job_id', return_value={}
    ):
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


def test_status_shows_a_column_per_swept_key():
    task_args = {
        'aaaa-1111': {'rupture_set': 'A', 'deformation_model': 'geologic'},
        'bbbb-2222': {'rupture_set': 'B', 'deformation_model': 'geologic'},
    }
    with patch.object(batch_cli, 'jobs_for_general_task', return_value=SUMMARIES), patch.object(
        batch_cli, 'task_args_by_job_id', return_value=task_args
    ):
        result = runner.invoke(runzi_cli.app, ['batch', 'status', GT_ID])

    assert result.exit_code == 0
    out = strip_ansi(result.output)
    assert 'rupture_set' in out  # swept -> a column
    assert 'deformation_model' not in out  # constant -> no column
    assert 'Job Name' not in out  # dropped
    # each job's swept value is on its row
    assert re.search(r'aaaa-1111.*\bA\b', out)
    assert re.search(r'bbbb-2222.*\bB\b', out)


def test_status_has_no_swept_columns_when_nothing_varies():
    task_args = {
        'aaaa-1111': {'rupture_set': 'A'},
        'bbbb-2222': {'rupture_set': 'A'},
    }
    with patch.object(batch_cli, 'jobs_for_general_task', return_value=SUMMARIES), patch.object(
        batch_cli, 'task_args_by_job_id', return_value=task_args
    ):
        result = runner.invoke(runzi_cli.app, ['batch', 'status', GT_ID])

    assert result.exit_code == 0
    assert 'rupture_set' not in strip_ansi(result.output)


def test_status_handles_describe_access_denied():
    err = ClientError({'Error': {'Code': 'AccessDeniedException', 'Message': 'not authorized'}}, 'DescribeJobs')
    with patch.object(batch_cli, 'jobs_for_general_task', return_value=SUMMARIES), patch.object(
        batch_cli, 'task_args_by_job_id', side_effect=err
    ):
        result = runner.invoke(runzi_cli.app, ['batch', 'status', GT_ID])

    assert result.exit_code == 1
    assert 'batch:DescribeJobs' in strip_ansi(result.output)


def test_log_writes_file_and_confirmation():
    with isolated_filesystem():
        with patch.object(batch_cli, 'job_log_events', return_value=iter(['line1', 'line2'])):
            result = runner.invoke(runzi_cli.app, ['batch', 'log', 'aaaa-1111'])
        assert result.exit_code == 0
        assert Path('aaaa-1111.log').read_text() == 'line1\nline2\n'
        out = strip_ansi(result.output)
        assert 'aaaa-1111.log' in out
        assert '2' in out  # line count


def test_log_reports_job_not_found():
    with isolated_filesystem():
        with patch.object(batch_cli, 'job_log_events', side_effect=JobNotFound('nope')):
            result = runner.invoke(runzi_cli.app, ['batch', 'log', 'nope'])
        assert result.exit_code == 1
        assert 'no' in strip_ansi(result.output).lower()
        assert not Path('nope.log').exists()


def test_log_reports_no_log_stream_yet():
    with isolated_filesystem():
        with patch.object(batch_cli, 'job_log_events', side_effect=LogStreamNotAvailable('j1')):
            result = runner.invoke(runzi_cli.app, ['batch', 'log', 'j1'])
        assert result.exit_code == 0
        assert 'no log' in strip_ansi(result.output).lower()
        assert not Path('j1.log').exists()


def test_log_handles_access_denied():
    err = ClientError({'Error': {'Code': 'AccessDeniedException', 'Message': 'x'}}, 'GetLogEvents')
    with isolated_filesystem():
        with patch.object(batch_cli, 'job_log_events', side_effect=err):
            result = runner.invoke(runzi_cli.app, ['batch', 'log', 'j1'])
        assert result.exit_code == 1
        assert 'logs:GetLogEvents' in strip_ansi(result.output)
