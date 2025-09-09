"""The command line functions for utilties."""

from pathlib import Path

import typer
from typing_extensions import Annotated

from runzi.runners import run_save_file_archive
from runzi.runners.save_file_archive import VALID_ROW

app = typer.Typer()


@app.command()
def save_file(
    target: Annotated[Path, typer.Argument(help="path of file to be archived")],
    tag: Annotated[str | None, typer.Option(help="add tag to metadata")] = None,
    input_csv_file: Annotated[
        bool, typer.Option(help=f"target is CSV list of files to archive; must have header: {VALID_ROW}")
    ] = False,
    output_csv_file: Annotated[
        Path | None, typer.Option(help="write CSV of archived files with assigned toshi IDs")
    ] = None,
    dry_run: Annotated[bool, typer.Option(help="mock run")] = False,
):
    """Zip a file and save as a ToshiAPI File object.allow_dash=

    Can provide single target file
    run_save_file_archive(target, tag, input_csv_file, output_csv_file, dry_run)
    """
    run_save_file_archive(target, tag, input_csv_file, output_csv_file, dry_run)


if __name__ == "__main__":
    app()
