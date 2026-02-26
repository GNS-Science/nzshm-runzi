"""Command line functions for calculationg hazard realizations."""

import logging
from pathlib import Path

# import gql
import typer
from rich import print as rich_print

from runzi.arguments import ArgSweeper
from runzi.tasks.oq_hazard import OQDisaggArgs, OQDisaggJobRunner, OQHazardArgs, OQHazardJobRunner

# logging.getLogger("gql").setLevel(logging.INFO)

app = typer.Typer()


@app.command()
def oq_hazard(input_filepath: Path):
    """Calculate hazard realizations using the OpenQuake engine."""
    rich_print("[yellow]Starting hazard jobs.")
    job_input = ArgSweeper.from_config_file(input_filepath, OQHazardArgs)
    runner = OQHazardJobRunner(job_input)
    gt_id = runner.run_jobs()
    rich_print(f"General Task ID: [bold green]{gt_id}")


@app.command()
def oq_disagg(input_filepath: Path):
    """Calculate hazard disaggregation realizations using the OpenQuake engine."""
    rich_print("[yellow]Starting disaggregation jobs.")
    job_input = ArgSweeper.from_config_file(input_filepath, OQDisaggArgs)
    runner = OQDisaggJobRunner(job_input)
    gt_id = runner.run_jobs()
    rich_print(f"General Task ID: [bold green]{gt_id}")


if __name__ == "__main__":
    app()
