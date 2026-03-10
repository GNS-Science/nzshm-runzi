"""Command line functions for post processing of inversions."""

from pathlib import Path

import typer
from rich import print as rich_print

from runzi.arguments import ArgSweeper
from runzi.cli import cluster_mode_callback
from runzi.tasks.average_solutions import AverageSolutionsArgs, AverageSolutionsJobRunner
from runzi.tasks.oq_opensha_convert import OQConvertArgs, OQConvertJobRunner
from runzi.tasks.scale_solution import ScaleSolutionArgs, ScaleSolutionJobRunner
from runzi.tasks.time_dependent_solution import TimeDependentSolutionArgs, TimeDependentSolutionJobRunner

app = typer.Typer()
app.callback()(cluster_mode_callback)


@app.command()
def avg_sol(input_filepath: Path):
    """Average multiple solutions by taking the mean rate of all ruptures."""
    rich_print("[yellow]Starting average solutions jobs.")
    job_input = ArgSweeper.from_config_file(input_filepath, AverageSolutionsArgs)
    runner = AverageSolutionsJobRunner(job_input)
    gt_id = runner.run_jobs()
    rich_print(f"General Task ID: [bold green]{gt_id}")


@app.command()
def time_dependent(input_filepath: Path):
    """Create time dependent inversion solutions by modifying rupture rates."""
    rich_print("[yellow]Starting time dependent solutions jobs.")
    job_input = ArgSweeper.from_config_file(input_filepath, TimeDependentSolutionArgs)
    runner = TimeDependentSolutionJobRunner(job_input)
    gt_id = runner.run_jobs()
    rich_print(f"General Task ID: [bold green]{gt_id}")


@app.command()
def scale(input_filepath: Path):
    """Scale rupture rates of inversion solutions."""
    rich_print("[yellow]Starting scale solutions jobs.")
    job_input = ArgSweeper.from_config_file(input_filepath, ScaleSolutionArgs)
    runner = ScaleSolutionJobRunner(job_input)
    gt_id = runner.run_jobs()
    rich_print(f"General Task ID: [bold green]{gt_id}")


@app.command()
def oq_convert(input_filepath: Path):
    """Convert OpenSHA inversion solutions to OpenQuake source input files."""
    rich_print("[yellow]Starting convert to OQ jobs.")
    job_input = ArgSweeper.from_config_file(input_filepath, OQConvertArgs)
    runner = OQConvertJobRunner(job_input)
    gt_id = runner.run_jobs()
    rich_print(f"General Task ID: [bold green]{gt_id}")


if __name__ == "__main__":
    app()
