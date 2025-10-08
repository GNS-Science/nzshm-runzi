"""Command line functions for generating diagnostic reports for rupture sets and inversions."""

import typer
from rich import print as rich_print
from typing_extensions import Annotated

from runzi.runners import run_diagnostic_reports

app = typer.Typer()


@app.command()
def rupture_set(
    toshi_id: Annotated[str, typer.Argument(help="id of rupture set or general task used to create rupture sets")],
):
    """Create diagnostic reports for rupture sets."""
    rich_print("[yellow]Starting rupture set report jobs.")
    run_diagnostic_reports(toshi_id, mode='rupture_set')


@app.command()
def inversion(general_task_id: str):
    """Create diagnostic reports for inversion."""
    rich_print("[yellow]Starting inversion report jobs.")
    run_diagnostic_reports(general_task_id, mode='inversion')


if __name__ == "__main__":
    app()
