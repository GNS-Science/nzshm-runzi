import datetime as dt
import os
import stat
from multiprocessing.dummy import Pool
from pathlib import PurePath
from subprocess import check_call

import boto3
import inquirer

from runzi.automation.scaling.file_utils import download_files, get_output_file_ids

# Set up your local config, from environment variables, with some sone defaults
from runzi.automation.scaling.local_config import (
    API_KEY,
    API_URL,
    CLUSTER_MODE,
    FATJAR,
    JAVA_THREADS,
    JVM_HEAP_MAX,
    JVM_HEAP_START,
    OPENSHA_JRE,
    OPENSHA_ROOT,
    S3_URL,
    USE_API,
    WORK_PATH,
    WORKER_POOL_SIZE,
    EnvMode,
)
from runzi.automation.scaling.opensha_task_factory import get_factory
from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.configuration.inversion_diagnostics import generate_tasks_or_configs


def inversion_diagnostic_runner(general_task_id):
    t0 = dt.datetime.utcnow()

    def call_script(script_name):
        print("call_script with:", script_name)
        if CLUSTER_MODE:
            check_call(['qsub', script_name])
        else:
            check_call(['bash', script_name])

    headers = {"x-api-key": API_KEY}
    file_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

    # BUILD_PLOTS = True
    # REPORT_LEVEL = 'DEFAULT' # None, 'LIGHT', 'DEFAULT', 'FULL'

    if CLUSTER_MODE == EnvMode['AWS']:
        batch_client = boto3.client(
            service_name='batch', region_name='us-east-1', endpoint_url='https://batch.us-east-1.amazonaws.com'
        )

    file_generator = get_output_file_ids(file_api, general_task_id)
    solutions = download_files(
        file_api,
        file_generator,
        str(WORK_PATH),
        overwrite=False,
        skip_existing=False,
        skip_download=(CLUSTER_MODE == EnvMode['AWS']),
    )

    scripts = []
    for script_file in generate_tasks_or_configs(general_task_id, solutions):
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

    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())


def inversion_diagnostic_query(*args):
    general_task_id = inquirer.text('General Task ID: ')
    confirm = inquirer.confirm(f'Confirm you want to run inversion diagnostics for ID: {general_task_id}')
    if confirm == True:
        inversion_diagnostic_runner(general_task_id)


if __name__ == '__main__':
    headers = {"x-api-key": API_KEY}
    file_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

    general_task_id = 'R2VuZXJhbFRhc2s6MTY5MDZxajVT'
    file_generator = get_output_file_ids(file_api, general_task_id)

    files = [f for f in file_generator]
    for f in files:
        print(files)
    solutions = download_files(file_api, files, str(WORK_PATH), overwrite=False, skip_existing=False)
    for s in solutions:
        print(s)
