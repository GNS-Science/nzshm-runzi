"""Command line functions for running inversions."""

from pathlib import Path

import typer
from rich import print as rich_print

from runzi.runners.inversion import run_inversion
from runzi.runners.inversion_inputs import CrustalInversionArgs, SubductionInversionArgs

app = typer.Typer()


@app.command()
def crustal(input_filepath: Path):
    """Run crustal inversions."""
    rich_print("[yellow]Starting crustal inversions.")
    job_input = CrustalInversionArgs.from_json_file(input_filepath)
    gt_id = run_inversion(job_input)
    rich_print(f"General Task ID: [bold green]{gt_id}")


@app.command()
def subduction(input_filepath: Path):
    """Run subduction inversions."""
    rich_print("[yellow]Starting subduction inversions.")
    job_input = SubductionInversionArgs.from_json_file(input_filepath)
    gt_id = run_inversion(job_input)
    rich_print(f"General Task ID: [bold green]{gt_id}")


if __name__ == "__main__":
    app()
