import argparse

from runzi.automation.scaling.file_utils import download_files, get_output_file_id
from runzi.automation.scaling.local_config import API_KEY, API_URL, S3_URL, WORK_PATH
from runzi.automation.scaling.toshi_api import CreateGeneralTaskArgs, ToshiApi


def prepare_inputs(file_id):
    """
    CHOOSE ONE OF:

     - file_generator = get_output_file_id(toshi_api, file_id)
     - file_generator = get_output_file_ids(general_api, upstream_task_id)
    """

    headers = {"x-api-key": API_KEY}
    toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

    # for a single rupture set, pass a valid FileID
    file_generator = get_output_file_id(toshi_api, file_id)  # for file by file ID

    rupture_sets = download_files(toshi_api, file_generator, str(WORK_PATH), overwrite=False)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("file_id")
    args = parser.parse_args()

    print(f"Attempt to download: ${args.file_id}")

    prepare_inputs(args.file_id)
