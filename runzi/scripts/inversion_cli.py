"""Command line functions for running inversions."""

import json
from pathlib import Path

import typer
from rich import print as rich_print

from runzi.cli.cli_helpers import from_json_format
from runzi.cli.config.config_builder import Config
from runzi.runners import run_crustal_inversion

app = typer.Typer()


def load_config(config_filepath: Path):
    loaded_config = json.loads(config_filepath.read_text())
    formatted_json = from_json_format(loaded_config)
    config = Config()
    config.from_json(formatted_json)
    return config


@app.command()
def crustal(input_filepath: Path):
    """Run crustal inversions."""
    rich_print("[yellow]Starting average solutions jobs.")
    job_input = load_config(input_filepath)
    gt_id = run_crustal_inversion(job_input)
    rich_print(f"General Task ID: [bold green]{gt_id}")


if __name__ == "__main__":
    app()
