#! python run_save_file.py
"""
a utility script to zip and save a file (with optional tag metadata) as a ToshiAPI File object

inputs:-
 - a path to the source file
 - tag to include in meta data
 - For ToshiAPI pass the ENV settings for the intended environment (PROD,TEST LOCAL)

"""
import argparse
import logging
import csv
import collections

from pathlib import Path
from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.automation.scaling.local_config import (WORK_PATH,
    USE_API, API_KEY, API_URL, S3_URL)
from runzi.util import archive

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

VALID_ROW = ['fullpath', 'grandparent', 'parent', 'filename']
DataRow = collections.namedtuple('DataRow', VALID_ROW)

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

def process_one_file(dry_run, filepath, tag=None):
    """Archive and upload one file."""

    log.info(f"Processing */{Path(filepath).name} :: {tag}")
    archive_path = None

    if not dry_run:
        archive_path = create_archive(filepath, WORK_PATH)
        log.info(f'archived {filepath} in {archive_path}.')

    if archive_path and USE_API:
        headers={"x-api-key":API_KEY}
        toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
        filename = Path(args.target).name
        meta = dict(filename=filename)
        if tag:
            meta['tag'] = str(tag)

        if not dry_run:
            archive_file_id, post_url = toshi_api.file.create_file(archive_path, meta=meta)
            toshi_api.file.upload_content(post_url, archive_path)
            log.info(f"pushed {archive_path} to ToshiAPI {API_URL} with id {archive_file_id}")

def process_file_list(args):
    with open(args.target, 'r') as csvfile:
        reader = csv.reader(csvfile)
        header = next(reader)
        if not header == VALID_ROW:
            log.error(f'file {arg.target} is not in the correct format.')
            return

        for datarow in map(lambda x: DataRow(*x), reader):
            process_one_file(args.dry_run, datarow.fullpath, tag=datarow.parent)

def parse_args():
    parser = argparse.ArgumentParser(description="""zip a file and save this as a ToshiAPI File object""")
    parser.add_argument("target", help="the path for the file ")
    parser.add_argument("-t", "--tag", help = "add tag to metadata")
    parser.add_argument("-i", "--input_csv_file", action="store_true",
        help = f"Get targets from CSV, must have header: {VALID_ROW}")
    parser.add_argument("-D", "--dry-run", action="store_true", help = f"mock run")

    args = parser.parse_args()
    return args

if __name__ == "__main__":

    args = parse_args()
    if args.input_csv_file:
        print(args)
        process_file_list(args)
    else:
        process_one_file(args.dry_run, args.target, args.tag)