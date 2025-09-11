"""The command line functions for utilties."""

from pathlib import Path

import typer
from rich import print as rich_print
from typing_extensions import Annotated

from runzi.runners import build_manual_index, run_save_file_archive
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
    """Zip a file and save as a ToshiAPI File object.

    Can provide single target file
    run_save_file_archive(target, tag, input_csv_file, output_csv_file, dry_run)
    """
    rich_print(f"[yellow]Saving file {target} to toshi API")
    run_save_file_archive(target, tag, input_csv_file, output_csv_file, dry_run)


@app.command()
def index_inv(
    gt_ids: Annotated[list[str], typer.Argument(help="whitespace seprated list of inversion genarl task IDs")],
):
    """Add inversions to the index (static web page)."""
    after_first = False
    for gt in gt_ids:
        rich_print(f"[yellow]Adding {gt} to the index.")
        build_manual_index(gt, 'INVERSION', after_first)
        after_first = True


if __name__ == "__main__":
    app()
