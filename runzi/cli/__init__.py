"""The CLI package for runzi"""

from typing import Annotated

import typer

from runzi.automation import local_config
from runzi.automation.local_config import EnvMode


def cluster_mode_callback(
    cluster_mode: Annotated[
        EnvMode, typer.Option(help="Execution target: LOCAL machine, HPC CLUSTER, or AWS cloud.")
    ] = local_config.DEFAULT_CLUSTER_MODE,
) -> None:
    # callback is used by both top runzi command and sub-commands so we
    # must check against default to avoid unwanted setting to default on sub-commands
    if cluster_mode is not local_config.DEFAULT_CLUSTER_MODE:
        local_config.CLUSTER_MODE = cluster_mode
