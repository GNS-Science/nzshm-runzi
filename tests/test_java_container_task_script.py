"""Regression tests for the AWS Batch Java container entrypoint (issue #333).

`docker/java_container_task.sh` launches the JVM gateway in the background, runs the python task,
then kills the JVM. If `kill -9 $!` is the script's last command the container always exits 0 (kill
succeeds), so AWS Batch marks failed jobs SUCCEEDED. These tests lock in that the script instead
captures the python task's exit status and re-raises it.
"""

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'docker' / 'java_container_task.sh'


def _script_text() -> str:
    return SCRIPT.read_text(encoding='utf-8')


def test_script_captures_and_reexports_python_status():
    text = _script_text()
    assert 'status=$?' in text
    assert 'exit $status' in text
    # the exit must come after the kill, so the JVM is still torn down before we return
    assert text.index('kill -9 $!') < text.index('exit $status')
    # and the kill must not be the last executable statement
    assert not text.rstrip().endswith('kill -9 $!')


@pytest.mark.skipif(
    sys.platform == 'win32',
    reason="linux AWS container script; Windows has no real bash (the `bash` shim is the WSL stub)",
)
def test_script_is_valid_bash():
    proc = subprocess.run(['bash', '-n', str(SCRIPT)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


@pytest.mark.skipif(
    sys.platform == 'win32',
    reason="exercises real bash exit-status semantics; Windows has no real bash",
)
def test_script_exit_status_is_the_python_status(tmp_path):
    """Drive the script with stubbed java/python/kill: a failing task must yield the task's exit code."""
    # Stubs replace the real launchers; env vars satisfy the paths the script references.
    env_setup = (
        'python3() { return 7; }\n'
        'java() { :; }\n'
        'kill() { return 0; }\n'
        f'export NZSHM22_SCRIPT_WORK_PATH={tmp_path}\n'
        'export NZSHM22_FATJAR=/nonexistent.jar\n'
        'export NZSHM22_SCRIPT_JVM_HEAP_MAX=1\n'
        'export NZSHM22_AWS_JAVA_THREADS=1\n'
        'export PYTHON_TASK_MODULE=does.not.matter\n'
        'export TASK_CONFIG_JSON_QUOTED=x\n'
    )
    harness = env_setup + _script_text()
    proc = subprocess.run(['bash', '-c', harness], capture_output=True, text=True)
    assert proc.returncode == 7, proc.stderr
