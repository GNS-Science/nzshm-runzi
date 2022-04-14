#! python run_save_oq_configuration_template.py
"""
a utility script to produce a zip archive of openquake configuration inputs
and save this as a ToshiAPI File object

inputs:-
 - a folder path where the inputs are available
 - all the files to clone in a self contained folder structure, whihc will be sip archived
 - the name of the configuration file for `oq engine --run CONFIG_FILENAME`
 - meta data as key-value pairs

- For ToshiAPI pass the ENV settings for the intended environment (PROD,TEST LOCAL)

"""
import argparse
import logging
import os
import zipfile
import datetime as dt
from dateutil.tz import tzutc

from pathlib import Path, PurePath
from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.automation.scaling.local_config import (WORK_PATH,
    USE_API, API_KEY, API_URL, S3_URL)

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def is_valid(source_path, config_filename):
    return Path(source_path).exists() and Path(source_path, config_filename).exists()

def archive(source_path, working_path, archive_name='config.zip'):
    '''
    zip contents of source path and return the full archive path.
    '''
    output_zip = Path(working_path, archive_name)
    zip = zipfile.ZipFile(output_zip, 'w')

    for root, dirs, files in os.walk(source_path):
        for file in files:
            filename = str(PurePath(root, file))
            arcname = str(filename).replace(source_path, '')
            zip.write(filename, arcname )

    return output_zip

def create_configuration_archive(source_path, config_filename, working_path):
    """
    verify source and if OK return the path to the zipped contents
    """
    log.info(f"create_configuration_archive source_path={source_path} working_path={working_path}")
    if is_valid(source_path, config_filename):
        return archive(source_path, working_path)
    else:
        raise Exception("source_path and/or config file do not exist.")

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="""produce a zip archive of openquake configuration inputs
and save this as a ToshiAPI File object""")
    parser.add_argument("config_folder", help="the path containing the configuration files")
    parser.add_argument("config_filename", help = "the main configuration filename, within the {config_folder} path")
    parser.add_argument("-t", "--tag", help = "add tag to metadata")
    args = parser.parse_args()

    archive_path = create_configuration_archive(args.config_folder, args.config_filename, WORK_PATH)

    if archive_path and USE_API:
        headers={"x-api-key":API_KEY}
        toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

        meta = dict(config_filename=args.config_filename, tag=args.tag)

        archive_file_id, post_url = toshi_api.file.create_file(archive_path, meta=meta)
        toshi_api.file.upload_content(post_url, archive_path)
        print(f"pushed {archive_file_id} to ToshiAPI {API_URL}")
    else:
        print(f'DONE, archived openquake configuration template in {archive_path}')
