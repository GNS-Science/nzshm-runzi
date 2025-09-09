import typer

from runzi.runners import run_rupset_diagnostics

app = typer.Typer()


@app.command()
def rupture_set(file_or_task_id: str, num_workers: int):
    """Create diagnostic reports for rupture sets."""
    run_rupset_diagnostics(file_or_task_id, num_workers)
