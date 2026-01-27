"""Command line functions for post processing of inversions."""

from pathlib import Path

import typer
from rich import print as rich_print
from runzi.execute.arguments import ArgSweeper

# from runzi.runners import (
    # ScaleSolutionsInput,
    # TimeDependentSolutionInput,
    # run_average_solutions,
    # run_oq_convert_solution,
    # run_scale_solution,
    # run_time_dependent_solution,
# )
from runzi.runners.runner_inputs import OQOpenSHAConvertArgs
from runzi.runners.average_solutions import AverageSolutionsJobRunner
from runzi.runners.scale_solution import ScaleSolutionJobRunner
from runzi.runners.time_dependent_solution import TimeDependentSolutionJobRunner
from runzi.runners.oq_convert_solution import OQConvertJobRunner
from runzi.execute.time_dependent_solution_task import TimeDependentSolutionInput
from runzi.execute.average_solutions_task import AverageSolutionsInput
from runzi.execute.scale_solution_task import ScaleSolutionInput
from runzi.execute.arguments import ArgSweeper
from runzi.execute.oq_opensha_convert_task import OQConvertInput

app = typer.Typer()


@app.command()
def avg_sol(input_filepath: Path):
    """Average multiple solutions by taking the mean rate of all ruptures."""
    rich_print("[yellow]Starting average solutions jobs.")
    job_input = ArgSweeper.from_config_file(input_filepath, AverageSolutionsInput)
    runner = AverageSolutionsJobRunner(job_input)
    gt_id = runner.run_jobs()
    rich_print(f"General Task ID: [bold green]{gt_id}")


@app.command()
def time_dependent(input_filepath: Path):
    """Create time dependent inversion solutions by modifying rupture rates."""
    rich_print("[yellow]Starting time dependent solutions jobs.")
    job_input = ArgSweeper.from_config_file(input_filepath, TimeDependentSolutionInput)
    runner = TimeDependentSolutionJobRunner(job_input)
    gt_id = runner.run_jobs()
    rich_print(f"General Task ID: [bold green]{gt_id}")


@app.command()
def scale(input_filepath: Path):
    """Scale rupture rates of inversion solutions."""
    rich_print("[yellow]Starting scale solutions jobs.")
    job_input = ArgSweeper.from_config_file(input_filepath, ScaleSolutionInput)
    runner = ScaleSolutionJobRunner(job_input)
    gt_id = runner.run_jobs()
    rich_print(f"General Task ID: [bold green]{gt_id}")


@app.command()
def oq_convert(input_filepath: Path):
    """Convert OpenSHA inversion solutions to OpenQuake source input files."""
    rich_print("[yellow]Starting convert to OQ jobs.")
    job_input = ArgSweeper.from_config_file(input_filepath, OQConvertInput)
    runner = OQConvertJobRunner(job_input)
    gt_id = runner.run_jobs()
    rich_print(f"General Task ID: [bold green]{gt_id}")


if __name__ == "__main__":
    app()
