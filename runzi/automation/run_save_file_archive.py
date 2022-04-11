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

from pathlib import Path
from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.automation.scaling.local_config import (WORK_PATH,
    USE_API, API_KEY, API_URL, S3_URL)
from runzi.util import archive

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def is_valid(source_path, config_filename):
    return Path(source_path).exists() and Path(source_path, config_filename).exists()

def create_archive(filename, working_path):
    """
    verify source and if OK return the path to the zipped contents
    """
    log.info(f"create_configuration_archive {filename}.zip in working_path={working_path}")
    if Path(filename).exists():
        return archive(filename, Path(working_path, f"{Path(filename).name}.zip"))
    else:
        raise Exception("file does not exist.")

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="""zip a file and save this as a ToshiAPI File object""")
    parser.add_argument("target", help="the path for the file")
    parser.add_argument("-t", "--tag", help = "add tag to metadata")
    #parser.add_argument("-t", "--tag", help = "add tag to metadata")
    args = parser.parse_args()

    archive_path = create_archive(args.target, WORK_PATH)

    if archive_path and USE_API:
        headers={"x-api-key":API_KEY}
        toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

        filename = Path(args.target).name
        meta = dict(filename=filename, tag=args.tag)

        archive_file_id, post_url = toshi_api.file.create_file(archive_path, meta=meta)
        toshi_api.file.upload_content(post_url, archive_path)
        print(f"pushed {archive_path} to ToshiAPI {API_URL} with id {archive_file_id}")
    else:
        print(f'DONE, archived openquake NRML XML in {archive_path}')
