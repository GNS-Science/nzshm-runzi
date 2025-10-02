import datetime as dt
from multiprocessing.dummy import Pool
from subprocess import check_call

import boto3

from runzi.automation.scaling.file_utils import download_files, get_output_file_ids

# Set up your local config, from environment variables, with some sone defaults
from runzi.automation.scaling.local_config import (
    API_KEY,
    API_URL,
    CLUSTER_MODE,
    S3_URL,
    WORK_PATH,
    WORKER_POOL_SIZE,
    EnvMode,
)
from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.configuration.inversion_diagnostics import generate_tasks_or_configs


def run_inversion_diagnostics(general_task_id: str):
    t0 = dt.datetime.now()

    def call_script(script_name):
        print("call_script with:", script_name)
        if CLUSTER_MODE:
            check_call(['qsub', script_name])
        else:
            check_call(['bash', script_name])


    # BUILD_PLOTS = True
    # REPORT_LEVEL = 'DEFAULT' # None, 'LIGHT', 'DEFAULT', 'FULL'

    if CLUSTER_MODE == EnvMode['AWS']:
        batch_client = boto3.client(
            service_name='batch', region_name='us-east-1', endpoint_url='https://batch.us-east-1.amazonaws.com'
        )

    scripts = []
    for script_file in generate_tasks_or_configs(general_task_id):
        print('scheduling: ', script_file)
        scripts.append(script_file)

    if CLUSTER_MODE == EnvMode['LOCAL']:
        print('task count: ', len(scripts))
        pool = Pool(WORKER_POOL_SIZE)
        pool.map(call_script, scripts)
        pool.close()
        pool.join()
    # print('worker count: ', WORKER_POOL_SIZE)

    elif CLUSTER_MODE == EnvMode['AWS']:
        for script_or_config in scripts:
            print('AWS_TIME!: ', script_or_config)
            res = batch_client.submit_job(**script_or_config)
            print(res)

    elif CLUSTER_MODE == EnvMode['CLUSTER']:
        for script_or_config in scripts:
            check_call(['qsub', script_or_config])

    print("Done! in %s secs" % (dt.datetime.now() - t0).total_seconds())
