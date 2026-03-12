"""The command line functions for generating rupture sets."""

from pathlib import Path

import typer
from rich import print as rich_print

from runzi.arguments import ArgSweeper
from runzi.tasks.coulomb_rupture_sets import CoulombRuptureSetArgs, CoulombRuptureSetJobRunner
from runzi.tasks.subduction_rupture_sets import SubductionRuptureSetArgs, SubductionRuptureSetJobRunner

app = typer.Typer()


@app.command()
def coulomb(input_filepath: Path):
    """Create Coulomb (crustal) rupture sets."""
    rich_print("[yellow]Starting Coulomb rupture set jobs.")
    job_input = ArgSweeper.from_config_file(input_filepath, CoulombRuptureSetArgs)
    runner = CoulombRuptureSetJobRunner(job_input)
    gt_id = runner.run_jobs()
    rich_print(f"General Task ID: [bold green]{gt_id}")


@app.command()
def subduction(input_filepath: Path):
    """Create subduction rupture sets."""
    rich_print("[yellow]Starting subduction rupture set jobs.")
    job_input = ArgSweeper.from_config_file(input_filepath, SubductionRuptureSetArgs)
    runner = SubductionRuptureSetJobRunner(job_input)
    gt_id = runner.run_jobs()
    rich_print(f"General Task ID: [bold green]{gt_id}")


if __name__ == "__main__":
    app()
