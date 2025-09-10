"""Command line functions for post processing of inversions."""

from pathlib import Path

import typer
from rich import print as rich_print

from runzi.runners import DisaggInput, HazardInput, run_oq_disagg, run_oq_hazard

app = typer.Typer()


@app.command()
def oq_hazard(input_filepath: Path):
    """Calculate hazard realizations using the OpenQuake engine."""
    rich_print("[yellow]Starting average solutions jobs.")
    job_input = HazardInput.from_toml(input_filepath)
    gt_id = run_oq_hazard(job_input)
    rich_print(f"General Task ID: [bold green]{gt_id}")


@app.command()
def oq_disagg(input_filepath: Path):
    """Calculate hazard disaggregation realizations using the OpenQuake engine."""
    rich_print("[yellow]Starting average solutions jobs.")
    job_input = DisaggInput.from_toml(input_filepath)
    gt_ids = run_oq_disagg(job_input)
    rich_print(f"General Task IDs: [bold green]{gt_ids}")


if __name__ == "__main__":
    app()
