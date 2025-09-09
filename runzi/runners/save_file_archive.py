"""
A utility script to zip and save a file (with optional tag metadata) as a ToshiAPI File object

inputs:-
 - a path to the source file
 - tag to include in meta data
 - For ToshiAPI pass the ENV settings for the intended environment (PROD,TEST LOCAL)
 - option to use csv list produced by nz-oq-distseis/list_nrmls.py script.

"""

import argparse
import collections
import csv
import logging
from pathlib import Path

from runzi.automation.scaling.local_config import API_KEY, API_URL, S3_URL, WORK_PATH
from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.util import archive

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

VALID_ROW = ['fullpath', 'grandparent', 'parent', 'filename']
VALID_ROW_OUT = VALID_ROW + ['toshi_id']

InputDataRow = collections.namedtuple('InputDataRow', VALID_ROW)  # type: ignore
OutputDataRow = collections.namedtuple('OutputDataRow', VALID_ROW_OUT)  # type: ignore


def is_valid(source_path, config_filename):
    return Path(source_path).exists() and Path(source_path, config_filename).exists()


def create_archive(filename, working_path):
    """
    verify source and if OK return the path to the zipped contents
    """
    log.info(f"create_archive {filename}.zip in working_path={working_path}")
    if Path(filename).exists():
        return archive(filename, Path(working_path, f"{Path(filename).name}.zip"))
    else:
        raise Exception("file does not exist.")


def process_one_file(dry_run: bool, filepath: str | Path, tag: str | None = None):
    """Archive and upload one file."""

    log.info(f"Processing */{Path(filepath).name} :: {tag}")
    archive_path = None

    if not dry_run:
        archive_path = create_archive(filepath, WORK_PATH)
        log.info(f'archived {filepath} in {archive_path}.')

    if archive_path:
        headers = {"x-api-key": API_KEY}
        toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
        filename = Path(filepath).name
        meta = dict(filename=filename)
        if tag:
            meta['tag'] = str(tag)

        archive_file_id = None
        if not dry_run:
            archive_file_id, post_url = toshi_api.file.create_file(archive_path, meta=meta)
            toshi_api.file.upload_content(post_url, archive_path)
            log.info(f"pushed {archive_path} to ToshiAPI {API_URL} with id {archive_file_id}")
        return archive_file_id


def process_file_list(
    target: Path,
    dry_run: bool,
):
    with open(target, 'r') as csvfile:
        reader = csv.reader(csvfile)
        header = next(reader)
        if not header == VALID_ROW:
            log.error(f'file {target} is not in the correct format.')

        for dr in map(lambda x: InputDataRow(*x), reader):
            toshi_id = process_one_file(dry_run, dr.fullpath, tag=dr.parent)  # type: ignore
            yield OutputDataRow(dr.fullpath, dr.grandparent, dr.parent, dr.filename, toshi_id)  # type: ignore


def parse_args():
    parser = argparse.ArgumentParser(description="""zip a file and save this as a ToshiAPI File object""")
    parser.add_argument("target", help="the path for the file ")
    parser.add_argument("-t", "--tag", help="add tag to metadata")
    parser.add_argument(
        "-i", "--input_csv_file", action="store_true", help=f"Get targets from CSV, must have header: {VALID_ROW}"
    )
    parser.add_argument("-D", "--dry-run", action="store_true", help="mock run")
    parser.add_argument("-o", "--output_csv_file", help="write out CSV, adding toshi_id to input csv")
    args = parser.parse_args()
    return vars(args)


def run_save_file_archive(
    target: Path,
    tag: str | None,
    input_csv_file: bool = False,
    output_csv_file: Path | None = None,
    dry_run: bool = False,
):
    if not input_csv_file:
        # just the one file
        process_one_file(dry_run, target, tag)
        return

    # read from input
    if input_csv_file:
        processed = process_file_list(target, dry_run)

    # write the output
    if input_csv_file and output_csv_file:
        with open(output_csv_file, 'w', newline='') as csvfile:
            _writer = csv.writer(csvfile)
            _writer.writerow(VALID_ROW_OUT)
            for p in processed:
                _writer.writerow([p.fullpath, p.grandparent, p.parent, p.filename, p.toshi_id])


if __name__ == "__main__":
    run_save_file_archive(**parse_args())
