import argparse
import json
from urllib.parse import unquote
from runzi.automation.scaling.toshi_api import ToshiApi, CreateGeneralTaskArgs
from runzi.automation.scaling.file_utils import download_files, get_output_file_id
from runzi.util.aws import get_secret

# Set up your local config, from environment variables, with some sone defaults
from runzi.automation.scaling.local_config import (WORK_PATH,
    API_URL, S3_URL, CLUSTER_MODE, EnvMode)
   
def prepare_inversion_inputs(json_config):
    """
    CHOOSE ONE OF:

     - file_generator = get_output_file_id(toshi_api, file_id)
     - file_generator = get_output_file_ids(general_api, upstream_task_id)
    """

    rupture_set_file_id = json.loads(unquote(json_config['containerOverrides']['environment'][0]['value']))['rupture_set_id']
   

    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

    # #for a single rupture set, pass a valid FileID
    file_generator = get_output_file_id(toshi_api, rupture_set_file_id) #for file by file ID

    rupture_sets = download_files(toshi_api, file_generator, str(WORK_PATH), overwrite=False)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("rupture_set_file_id")
    args = parser.parse_args()

    print(f"Attempt to download: ${args.rupture_set_file_id}")

    # #Get API key from AWS secrets manager
    if 'TEST' in API_URL.upper():
        API_KEY = get_secret("NZSHM22_TOSHI_API_SECRET_TEST", "us-east-1").get("NZSHM22_TOSHI_API_KEY_TEST")
    elif 'PROD' in API_URL.upper():
        API_KEY = get_secret("NZSHM22_TOSHI_API_SECRET_PROD", "us-east-1").get("NZSHM22_TOSHI_API_KEY_PROD")

    prepare_inversion_inputs(args.rupture_set_file_id)


