"""Command line functions for running inversions."""

from pathlib import Path

import typer
from rich import print as rich_print

from runzi.arguments import ArgSweeper
from runzi.cli import cluster_mode_callback
from runzi.tasks.inversion import (
    CrustalInversionArgs,
    CrustalInversionJobRunner,
    SubductionInversionArgs,
    SubductionInversionJobRunner,
)

app = typer.Typer()
app.callback()(cluster_mode_callback)


@app.command()
def crustal(input_filepath: Path):
    """Run crustal inversions."""
    rich_print("[yellow]Starting crustal inversions.")
    job_input = ArgSweeper.from_config_file(input_filepath, CrustalInversionArgs)
    runner = CrustalInversionJobRunner(job_input)
    gt_id = runner.run_jobs()
    rich_print(f"General Task ID: [bold green]{gt_id}")


@app.command()
def subduction(input_filepath: Path):
    """Run subduction inversions."""
    rich_print("[yellow]Starting subduction inversions.")
    job_input = ArgSweeper.from_config_file(input_filepath, SubductionInversionArgs)
    runner = SubductionInversionJobRunner(job_input)
    gt_id = runner.run_jobs()
    rich_print(f"General Task ID: [bold green]{gt_id}")


if __name__ == "__main__":
    app()
