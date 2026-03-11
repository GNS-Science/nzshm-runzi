"""The CLI package for runzi"""

from typing import Annotated

import typer

from runzi.automation import local_config
from runzi.automation.local_config import ClusterModeEnum


def cluster_mode_callback(
    cluster_mode: Annotated[
        ClusterModeEnum, typer.Option(help="Execution target: LOCAL machine, HPC CLUSTER, or AWS cloud.")
    ] = local_config.DEFAULT_CLUSTER_MODE,
) -> None:
    """Set the global cluster mode when explicitly provided by the user.

    This callback is registered on both the top-level `runzi` command and each
    sub-command (via `invoke_without_command` / typer callback chaining), so it
    runs for every invocation. To avoid silently resetting the cluster mode back
    to the default when a sub-command is invoked without `--cluster-mode`, we
    only update `local_config.CLUSTER_MODE` when the supplied value differs from
    the compiled-in default.
    """
    # callback is used by both top runzi command and sub-commands so we
    # must check against default to avoid unwanted setting to default on sub-commands
    if cluster_mode is not local_config.DEFAULT_CLUSTER_MODE:
        local_config.CLUSTER_MODE = cluster_mode
