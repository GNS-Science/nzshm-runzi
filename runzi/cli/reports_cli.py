"""Command line functions for generating diagnostic reports for rupture sets and inversions."""

import typer
from rich import print as rich_print
from typing_extensions import Annotated

from runzi.arguments import ArgSweeper
from runzi.tasks.inversion_report import InversionReportArgs, InversionReportJobRunner
from runzi.tasks.rupset_report import RupsetReportArgs, RupsetReportJobRunner

app = typer.Typer()


@app.command()
def rupset(
    toshi_id: Annotated[str, typer.Argument(help="id of rupture set or general task used to create rupture sets")],
):
    """Create diagnostic reports for rupture sets."""
    rich_print("[yellow]Starting rupture set report jobs.")

    # these values are place-holders and will be set by the runner
    prototype = RupsetReportArgs(source_solution_id=toshi_id, build_report_level=None)
    job_input = ArgSweeper(prototype_args=prototype, swept_args={}, title="", description="")
    runner = RupsetReportJobRunner(job_input)
    runner.run_jobs()


@app.command()
def inversion(general_task_id: str):
    """Create diagnostic reports for inversion."""
    rich_print("[yellow]Starting inversion report jobs.")

    # these values are place-holders and will be set by the runner
    prototype = InversionReportArgs(
        source_solution_id=general_task_id,
        build_mfd_plots=False,
        build_report_level=None,
        hack_fault_model=None,
    )
    job_input = ArgSweeper(prototype_args=prototype, swept_args={}, title="", description="")
    runner = InversionReportJobRunner(job_input)
    runner.run_jobs()


if __name__ == "__main__":
    app()
