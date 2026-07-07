"""Tests for OpenshaTaskFactory bash-script generation.

After the gateway-port refactor the LOCAL/CLUSTER launcher picks a free port at runtime (like the AWS
container script) and exports NZSHM22_APP_PORT; the per-task index is used only for config/log
filenames (matching the sibling PythonTaskFactory). The java log filename must stay keyed to the
runtime port because inversion_solution_builder uploads that file by name.
"""

import subprocess
import sys

import pytest

import runzi.build_tasks as a_module
from runzi.automation.opensha_task_factory import OpenshaTaskFactory


def _factory(tmp_path):
    return OpenshaTaskFactory.create(
        root_path=tmp_path,
        working_path=tmp_path,
        python_script_module=a_module,
        jre_path='/opt/java/bin',
        app_jar_path='/opt/app.jar',
        task_config_path=tmp_path,
    )


def test_bash_script_picks_free_port_at_runtime(tmp_path):
    script = _factory(tmp_path).get_task_script()
    assert 'export NZSHM22_APP_PORT=$(' in script  # runtime command substitution, not a fixed port
    assert 's.getsockname()[1]' in script


def test_java_log_filename_follows_runtime_port(tmp_path):
    """The uploader looks for java_app.<port>.log by the runtime port, so the launcher must write it
    under that same runtime port, not the build-time task index."""
    script = _factory(tmp_path).get_task_script()
    assert 'java_app.${NZSHM22_APP_PORT}.log' in script


def test_config_filename_uses_task_index_starting_at_one(tmp_path):
    factory = _factory(tmp_path)
    first = factory.get_task_script()
    second = factory.get_task_script()
    assert 'config.1.json' in first
    assert 'config.2.json' in second


def test_generated_script_propagates_python_exit_status(tmp_path):
    """The launcher must exit with the python task's status, not the trailing kill's (issue #333).

    A bare `kill -9 $!` as the final command would always exit 0 (kill succeeds), masking task
    failures from the LOCAL/CLUSTER caller (`check_call(['bash', script])`)."""
    script = _factory(tmp_path).get_task_script()
    # capture python's status right after its invocation, before the kill can clobber $?
    assert 'python_script.1.log\nstatus=$?\n' in script
    # the JVM kill must not be the last command...
    assert not script.rstrip().endswith('kill -9 $!')
    # ...instead the script ends by re-raising the captured status
    assert script.rstrip().endswith('exit $status')


def test_script_waits_for_gateway_between_java_and_python(tmp_path):
    """The client must not start until the JVM gateway is listening.

    py4j does a single, non-retrying connect on the client's first call, so launching python before
    the JVM binds its port fails the whole task with ConnectionRefusedError (the race is worst on a
    cold JVM/disk cache; e.g. coulomb connects in its __init__). The launcher must run the shared
    readiness wait after the backgrounded java launch and before the python client. (The wait's own
    behaviour is covered by tests/test_wait_for_gateway.py.)"""
    script = _factory(tmp_path).get_task_script()
    assert 'JAVA_PID=$!' in script
    assert '-m runzi.automation.wait_for_gateway' in script
    assert (
        script.index('JAVA_PID=$!') < script.index('runzi.automation.wait_for_gateway') < script.index('config.1.json')
    )


@pytest.mark.skipif(
    sys.platform == 'win32',
    reason="generated script targets unix launchers (LOCAL/CLUSTER) and the linux AWS container; "
    "Windows has no real bash (the `bash` shim is the WSL installer stub)",
)
def test_generated_script_is_valid_bash(tmp_path):
    script = _factory(tmp_path).get_task_script()
    proc = subprocess.run(['bash', '-n'], input=script, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stderr


@pytest.mark.skipif(
    sys.platform == 'win32',
    reason="exercises real bash exit-status semantics; Windows has no real bash",
)
def test_generated_script_exit_status_is_the_python_status(tmp_path):
    """Functionally confirm a failing task yields a non-zero script exit (would be 0 before the fix)."""
    script = _factory(tmp_path).get_task_script()
    # Stub out the real launchers so we can drive exit semantics without java/python: a failing task
    # (python3 -> exit 7) followed by a successful kill must leave the script exiting 7, not 0.
    harness = 'python3() { return 7; }\njava() { :; }\nkill() { return 0; }\n' + script
    proc = subprocess.run(['bash', '-c', harness], capture_output=True, text=True)
    assert proc.returncode == 7, proc.stderr
