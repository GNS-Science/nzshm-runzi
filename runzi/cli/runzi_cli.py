"""The main runzi CLI script"""

from typing import Annotated

import typer

from runzi.automation import local_config
from runzi.automation.local_config import ClusterModeEnum
from runzi.cli import hazard_cli, inversion_cli, inversion_post_process_cli, reports_cli, rupture_sets_cli, utils_cli

app = typer.Typer(help="The NZ NSHM runzi CLI.", no_args_is_help=True)


# Register a callback so we can add a command line flag (option) to the runzi app
# (e.g. `runzi inversion --cluster-mode CLUSTER run ...`).
@app.callback()
def cluster_mode_callback(
    cluster_mode: Annotated[
        ClusterModeEnum, typer.Option(help="Execution target: LOCAL machine, HPC CLUSTER, or AWS cloud.")
    ] = local_config.DEFAULT_CLUSTER_MODE,
) -> None:
    """Set the global cluster mode when explicitly provided by the user.

    local_config.CLUSTER_MODE is used by the build, schedule task, etc. modules. The value of
    CLUSTER_MODE dictates behavior which is specific to the platform the jobs are run on.
    """
    local_config.CLUSTER_MODE = cluster_mode


app.add_typer(inversion_cli.app, name="inversion", help="inversion", no_args_is_help=True)
app.add_typer(hazard_cli.app, name="hazard", help="hazard calculations", no_args_is_help=True)
app.add_typer(inversion_post_process_cli.app, name="ipp", help="inversion post processing", no_args_is_help=True)
app.add_typer(rupture_sets_cli.app, name="rupset", help="create rupture sets", no_args_is_help=True)
app.add_typer(reports_cli.app, name="reports", help="create inversion and rupture set reports", no_args_is_help=True)
app.add_typer(utils_cli.app, name="utils", help="utilities", no_args_is_help=True)

if __name__ == "__main__":
    app()
