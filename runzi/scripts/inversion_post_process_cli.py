"""Command line functions for post processing of inversions."""

from pathlib import Path
from typing import Optional

import typer
from rich import print as rich_print
from typing_extensions import Annotated

from runzi.runners import (
    AverageSolutionsInput,
    ScaleSolutionsInput,
    TimeDependentSolutionInput,
    run_average_solutions,
    run_oq_convert_solution,
    run_scale_solution,
    run_time_dependent_solution,
)

app = typer.Typer()


@app.command()
def avg_sol(input_filepath: Path):
    """Average multiple solutions by taking the mean rate of all ruptures."""
    rich_print("[yellow]Starting average solutions jobs.")
    job_input = AverageSolutionsInput.from_toml(input_filepath)
    gt_id = run_average_solutions(job_input)
    rich_print(f"General Task ID: [bold green]{gt_id}")


@app.command()
def time_dependent(input_filepath: Path):
    """Create time dependent inversion solutions by modifying rupture rates."""
    rich_print("[yellow]Starting time dependent solutions jobs.")
    job_input = TimeDependentSolutionInput.from_toml(input_filepath)
    gt_id = run_time_dependent_solution(job_input)
    rich_print(f"General Task ID: [bold green]{gt_id}")


@app.command()
def scale(input_filepath: Path):
    """Scale rupture rates of inversion solutions."""
    rich_print("[yellow]Starting scale solutions jobs.")
    job_input = ScaleSolutionsInput.from_toml(input_filepath)
    gt_id = run_scale_solution(job_input)
    rich_print(f"General Task ID: [bold green]{gt_id}")


@app.command()
def oq_convert(
    title: str,
    description: str,
    ids: Annotated[
        list[str],
        typer.Argument(
            help=(
                "Whitespace seperated list of IDs of objects to convert. "
                "Can be individual InversionSolutions or GeneralTask."
            )
        ),
    ],
    num_workers: Optional[int] = None,
):
    """Convert OpenSHA inversion solutions to OpenQuake source input files."""
    rich_print("[yellow]Starting convert to OQ jobs.")
    gt_id = run_oq_convert_solution(ids, title, description, num_workers)
    rich_print(f"General Task ID: [bold green]{gt_id}")


if __name__ == "__main__":
    app()
