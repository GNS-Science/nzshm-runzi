"""The command line functions for generating rupture sets."""

from pathlib import Path

import typer
from rich import print as rich_print

from runzi.runners import (
    CoulombRuptureSetsInput,
    SubductionRuptureSetsInput,
    run_coulomb_rupture_sets,
    run_subduction_rupture_sets,
)

app = typer.Typer()


@app.command()
def coulomb_rupset(input_filepath: Path):
    """Create Coulomb (crustal) rupture sets."""
    rich_print("[yellow]Starting Coulomb rupture set jobs.")
    job_input = CoulombRuptureSetsInput.from_toml(input_filepath)
    gt_id = run_coulomb_rupture_sets(job_input)
    rich_print(f"General Task ID: [bold green]{gt_id}")


@app.command()
def sub_rupset(input_filepath: Path):
    """Create subduction rupture sets."""
    rich_print("[yellow]Starting subduction rupture set jobs.")
    job_input = SubductionRuptureSetsInput.from_toml(input_filepath)
    gt_id = run_subduction_rupture_sets(job_input)
    rich_print(f"General Task ID: [bold green]{gt_id}")


if __name__ == "__main__":
    app()
