"""Command line functions for running inversions."""

import json
from pathlib import Path

import typer
from rich import print as rich_print

from runzi.runners import run_crustal_inversion, run_subduction_inversion
from runzi.runners.inversion_inputs import SubductionInversionArgs, CrustalInversionArgs

app = typer.Typer()


@app.command()
def crustal(input_filepath: Path):
    """Run crustal inversions."""
    rich_print("[yellow]Starting crustal inversions.")
    job_input = CrustalInversionArgs.from_json_file(input_filepath)
    gt_id = run_crustal_inversion(job_input)
    rich_print(f"General Task ID: [bold green]{gt_id}")


@app.command()
def subduction(input_filepath: Path):
    """Run subduction inversions."""
    rich_print("[yellow]Starting subduction inversions.")
    job_input = SubductionInversionArgs.from_json_file(input_filepath)
    gt_id = run_subduction_inversion(job_input)
    rich_print(f"General Task ID: [bold green]{gt_id}")


if __name__ == "__main__":
    app()
