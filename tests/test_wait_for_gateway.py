"""Tests for the shared JVM-gateway readiness wait (runzi.automation.wait_for_gateway).

Both Java-task launchers (the LOCAL/CLUSTER bash from OpenshaTaskFactory and the AWS Batch
docker/java_container_task.sh) call this module before starting the Python client, because py4j does
a single, non-retrying connect and would otherwise race a still-booting JVM (coulomb connects in its
__init__ and lost that race). These tests drive the function directly rather than through bash.
"""

import socket
import subprocess
import sys
import threading
import time

from runzi.automation.wait_for_gateway import main, wait_for_gateway


def _free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _listener():
    """A bound, listening socket standing in for the JVM gateway; caller closes it."""
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('127.0.0.1', 0))
    srv.listen(1)
    return srv, srv.getsockname()[1]


def test_returns_true_when_port_is_already_listening():
    srv, port = _listener()
    try:
        assert wait_for_gateway(port, timeout=5) is True
    finally:
        srv.close()


def test_blocks_until_a_late_listener_comes_up():
    """The whole point of the fix: don't return until the gateway is actually accepting connections."""
    port = _free_port()

    def late_bind():
        time.sleep(0.6)
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('127.0.0.1', port))
        s.listen(1)
        time.sleep(2)
        s.close()

    threading.Thread(target=late_bind, daemon=True).start()
    start = time.monotonic()
    assert wait_for_gateway(port, timeout=5) is True
    assert time.monotonic() - start >= 0.5, "returned before the late listener bound the port"


def test_times_out_when_nothing_ever_listens():
    port = _free_port()  # nobody binds it
    start = time.monotonic()
    assert wait_for_gateway(port, timeout=0.6) is False
    assert time.monotonic() - start >= 0.5


def test_bails_fast_when_gateway_process_dies():
    """A JVM that exits before binding must make the wait give up quickly, not run to the timeout."""
    port = _free_port()  # nobody ever binds it
    dead = subprocess.Popen([sys.executable, '-c', 'pass'])
    dead.wait()  # ensure it has exited before we start polling
    start = time.monotonic()
    assert wait_for_gateway(port, pid=dead.pid, timeout=30) is False
    assert time.monotonic() - start < 3, "did not bail on the dead gateway pid"


def test_main_returns_zero_when_listening():
    srv, port = _listener()
    try:
        assert main([str(port)]) == 0
    finally:
        srv.close()


def test_main_returns_one_when_gateway_dies():
    dead = subprocess.Popen([sys.executable, '-c', 'pass'])
    dead.wait()
    assert main([str(_free_port()), str(dead.pid)]) == 1


def test_main_returns_usage_error_without_args():
    assert main([]) == 2
