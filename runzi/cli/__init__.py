"""The CLI package for runzi"""

from typing import Optional

import typer

from runzi.automation import local_config
from runzi.automation.local_config import EnvMode


def cluster_mode_callback(
    cluster_mode: Optional[EnvMode] = typer.Option(
        None, help="Execution target: LOCAL machine, HPC CLUSTER, or AWS cloud."
    )
) -> None:
    if cluster_mode is not None:
        local_config.CLUSTER_MODE = cluster_mode
