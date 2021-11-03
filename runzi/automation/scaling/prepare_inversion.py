import argparse
from runzi.automation.scaling.toshi_api import ToshiApi, CreateGeneralTaskArgs
from runzi.automation.scaling.file_utils import download_files, get_output_file_id

# Set up your local config, from environment variables, with some sone defaults
from runzi.automation.scaling.local_config import (WORK_PATH,
    API_KEY, API_URL, S3_URL, CLUSTER_MODE, EnvMode)
   
def prepare_inversion_inputs(rupture_set_file_id):
    """
    CHOOSE ONE OF:

     - file_generator = get_output_file_id(toshi_api, file_id)
     - file_generator = get_output_file_ids(general_api, upstream_task_id)
    """

    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

    #for a single rupture set, pass a valid FileID
    file_generator = get_output_file_id(toshi_api, rupture_set_file_id) #for file by file ID

    rupture_sets = download_files(toshi_api, file_generator, str(WORK_PATH), overwrite=False)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("rupture_set_file_id")
    args = parser.parse_args()

    print(f"Attempt to download: ${args.rupture_set_file_id}")
    prepare_inversion_inputs(args.rupture_set_file_id)


