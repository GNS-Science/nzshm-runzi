"""Command line functions for generating diagnostic reports for rupture sets and inversions."""

import typer
from rich import print as rich_print

from runzi.runners import run_inversion_diagnostics, run_rupset_diagnostics

app = typer.Typer()


@app.command()
def rupture_set(file_or_task_id: str, num_workers: int):
    """Create diagnostic reports for rupture sets."""
    rich_print("[yellow]Starting rupture set report jobs.")
    run_rupset_diagnostics(file_or_task_id, num_workers)


@app.command()
def inversion(general_task_id: str):
    """Create diagnostic reports for inversion."""
    rich_print("[yellow]Starting inversion report jobs.")
    run_inversion_diagnostics(general_task_id)


if __name__ == "__main__":
    app()
