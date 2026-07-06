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


@pytest.mark.skipif(
    sys.platform == 'win32',
    reason="generated script targets unix launchers (LOCAL/CLUSTER) and the linux AWS container; "
    "Windows has no real bash (the `bash` shim is the WSL installer stub)",
)
def test_generated_script_is_valid_bash(tmp_path):
    script = _factory(tmp_path).get_task_script()
    proc = subprocess.run(['bash', '-n'], input=script, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stderr
