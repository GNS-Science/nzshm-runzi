"""Command line functions for post processing of inversions."""

from pathlib import Path

import typer
from rich import print as rich_print

from runzi.runners import (
    ScaleSolutionsInput,
    TimeDependentSolutionInput,
    run_average_solutions,
    run_oq_convert_solution,
    run_scale_solution,
    run_time_dependent_solution,
)
from runzi.runners.runner_inputs import AverageSolutionsInput, OQOpenSHAConvertArgs

app = typer.Typer()


@app.command()
def avg_sol(input_filepath: Path):
    """Average multiple solutions by taking the mean rate of all ruptures."""
    rich_print("[yellow]Starting average solutions jobs.")
    job_input = AverageSolutionsInput.from_toml_file(input_filepath)
    gt_id = run_average_solutions(job_input)
    rich_print(f"General Task ID: [bold green]{gt_id}")


@app.command()
def time_dependent(input_filepath: Path):
    """Create time dependent inversion solutions by modifying rupture rates."""
    rich_print("[yellow]Starting time dependent solutions jobs.")
    job_input = TimeDependentSolutionInput.from_toml_file(input_filepath)
    gt_id = run_time_dependent_solution(job_input)
    rich_print(f"General Task ID: [bold green]{gt_id}")


@app.command()
def scale(input_filepath: Path):
    """Scale rupture rates of inversion solutions."""
    rich_print("[yellow]Starting scale solutions jobs.")
    job_input = ScaleSolutionsInput.from_toml_file(input_filepath)
    gt_id = run_scale_solution(job_input)
    rich_print(f"General Task ID: [bold green]{gt_id}")


@app.command()
def oq_convert(input_filepath: Path):
    """Convert OpenSHA inversion solutions to OpenQuake source input files."""
    rich_print("[yellow]Starting convert to OQ jobs.")
    job_input = OQOpenSHAConvertArgs.from_toml_file(input_filepath)
    gt_id = run_oq_convert_solution(job_input)
    rich_print(f"General Task ID: [bold green]{gt_id}")


if __name__ == "__main__":
    app()
