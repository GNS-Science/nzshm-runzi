import argparse
import json
from urllib.parse import unquote
from pathlib import PurePath
from subprocess import check_call
from multiprocessing.dummy import Pool

import datetime as dt
from dateutil.tz import tzutc

from runzi.automation.scaling.toshi_api import ToshiApi

from runzi.automation.scaling.opensha_task_factory import OpenshaTaskFactory
from runzi.automation.scaling.file_utils import download_files, get_output_file_id
from runzi.automation.run_inversion_diagnostics import run_tasks
from runzi.aws_client.upload import upload_to_bucket

# Set up your local config, from environment variables, with some sone defaults
from runzi.automation.scaling.local_config import (OPENSHA_ROOT, WORK_PATH, OPENSHA_JRE, FATJAR,
    JVM_HEAP_MAX, JVM_HEAP_START, USE_API, JAVA_THREADS,
    API_KEY, API_URL, S3_URL, CLUSTER_MODE, MOCK_MODE)

    
def run_inversion_diags(file_id):    
    
    t0 = dt.datetime.utcnow()

    GENERAL_TASK_ID = None
    # If you wish to override something in the main config, do so here ..
    WORKER_POOL_SIZE = 3
    JVM_HEAP_MAX = 15
    JAVA_THREADS = 4
    # USE_API = True #to read the ruptset form the API


    #If using API give this task a descriptive setting...
    TASK_TITLE = "Inversion diags"
    TASK_DESCRIPTION = """
    """

    def call_script(script_name):
        print("call_script with:", script_name)
        if not MOCK_MODE:
            if CLUSTER_MODE:
                check_call(['qsub', script_name])
            else:
                check_call(['bash', script_name])

    headers={"x-api-key":API_KEY}
    file_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

    BUILD_PLOTS = True
    REPORT_LEVEL = 'DEFAULT' # None, 'LIGHT', 'DEFAULT', 'FULL'

    pool = Pool(WORKER_POOL_SIZE)
    for inversion_task_id in [file_id]: #"R2VuZXJhbFRhc2s6Mjc4OXphVmN2"]: #, "R2VuZXJhbFRhc2s6MjY4M1FGajVh"]:
        #get input files from API
        file_generator = get_output_file_id(file_api, inversion_task_id) #
        solutions = download_files(file_api, file_generator, str(WORK_PATH), overwrite=False, skip_existing=False)

        print("GENERAL_TASK_ID:", GENERAL_TASK_ID)

        #print('SOLUTIONS', solutions)
        scripts = []
        for script_file in run_tasks(GENERAL_TASK_ID, solutions):
            print('scheduling: ', script_file)
            scripts.append(script_file)

        print('task count: ', len(scripts))
        pool.map(call_script, scripts)

    print('worker count: ', WORKER_POOL_SIZE)

    pool.close()
    pool.join()

    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())
    upload_to_bucket(file_id, 'nzshm-static-reports-test')

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    args = parser.parse_args()
    file_id = json.loads(unquote(args.config))['rupture_set_id']
    run_inversion_diags(file_id)