import datetime as dt
import getpass
from multiprocessing.dummy import Pool
from pathlib import PurePath
from subprocess import check_call
from typing import TYPE_CHECKING

import boto3

from runzi.automation.scaling.file_utils import download_files, get_output_file_id

# Set up your local config, from environment variables, with some sone defaults
from runzi.automation.scaling.local_config import API_KEY, API_URL, CLUSTER_MODE, S3_URL, WORK_PATH, EnvMode, USE_API
from runzi.automation.scaling.toshi_api import CreateGeneralTaskArgs, ModelType, SubtaskType, ToshiApi
from runzi.configuration.subduction_inversions import build_subduction_tasks

if TYPE_CHECKING:
    from runzi.runners.inversion_inputs_v2 import InversionInput


def run_subduction_inversion(inversion_input: 'InversionInput') -> str | None:
    t0 = dt.datetime.now()

    worker_pool_size = inversion_input.job.worker_pool_size
    task_title = inversion_input.general.task_title
    task_description = inversion_input.general.task_description
    model_type = inversion_input.general.model_type
    subtask_type = inversion_input.general.subtask_type

    work_path: str | PurePath
    if CLUSTER_MODE == EnvMode['AWS']:
        work_path = '/WORKING'
    else:
        work_path = WORK_PATH

    headers = {"x-api-key": API_KEY}
    toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

    args = inversion_input.get_run_args()
    args_list = []
    for key, value in args.items():
        args_list.append(dict(k=key, v=value))

    general_task_id: str | None = None
    if USE_API:
        # create new task in toshi_api
        gt_args = (
            CreateGeneralTaskArgs(agent_name=getpass.getuser(), title=task_title, description=task_description)
            .set_argument_list(args_list)
            .set_subtask_type(subtask_type)
            .set_model_type(model_type)
        )

        general_task_id = toshi_api.general_task.create_task(gt_args)

    if CLUSTER_MODE == EnvMode['AWS']:
        batch_client = boto3.client(
            service_name='batch', region_name='us-east-1', endpoint_url='https://batch.us-east-1.amazonaws.com'
        )

    print("GENERAL_TASK_ID:", general_task_id)

    scripts = []
    for script_file in build_subduction_tasks(general_task_id, inversion_input):
        scripts.append(script_file)

    if CLUSTER_MODE == EnvMode['LOCAL']:

        def call_script(script_or_config):
            print("call_script with:", script_or_config)
            check_call(['bash', script_or_config])

        print('task count: ', len(scripts))
        print('worker count: ', worker_pool_size)
        pool = Pool(worker_pool_size)
        pool.map(call_script, scripts)
        pool.close()
        pool.join()

    elif CLUSTER_MODE == EnvMode['AWS']:
        for script_or_config in scripts:
            # print('AWS_TIME!: ', script_or_config)
            res = batch_client.submit_job(**script_or_config)
            print(res)

    elif CLUSTER_MODE == EnvMode['CLUSTER']:
        for script_or_config in scripts:
            check_call(['qsub', script_or_config])

    print("Done! in %s secs" % (dt.datetime.now() - t0).total_seconds())
    print("GENERAL_TASK_ID:", general_task_id)

    return general_task_id
