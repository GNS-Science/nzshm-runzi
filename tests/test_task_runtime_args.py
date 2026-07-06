"""Tests for TaskRuntimeArgs.java_gateway_port.

The py4j gateway port is a runtime property of the JVM process, owned by whichever launcher starts
it: on AWS Batch (forced host networking) java_container_task.sh picks a free port per container; on
LOCAL/CLUSTER the generated bash script exports its per-task port. Both export NZSHM22_APP_PORT, and
TaskRuntimeArgs reads it — so the port is never shipped through the config, and there is one runtime
source of truth shared by the JVM and the Python client.
"""

import pytest

from runzi.arguments import TaskRuntimeArgs


def test_java_gateway_port_reads_app_port_env(monkeypatch):
    monkeypatch.setenv('NZSHM22_APP_PORT', '51234')
    args = TaskRuntimeArgs(use_api=True)
    assert args.java_gateway_port == 51234


def test_java_gateway_port_not_serialized(monkeypatch):
    """The port is derived at runtime, so it must not appear in the config the submitter ships."""
    monkeypatch.setenv('NZSHM22_APP_PORT', '51234')
    args = TaskRuntimeArgs(use_api=True)
    assert 'java_gateway_port' not in args.model_dump()


def test_java_gateway_port_errors_when_env_unset(monkeypatch):
    """Reading the port without a launcher having exported it is a misconfiguration, not a default."""
    monkeypatch.delenv('NZSHM22_APP_PORT', raising=False)
    args = TaskRuntimeArgs(use_api=True)
    with pytest.raises(RuntimeError):
        _ = args.java_gateway_port
