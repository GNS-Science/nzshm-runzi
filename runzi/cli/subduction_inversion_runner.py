import datetime as dt
import os
from multiprocessing.dummy import Pool
from subprocess import check_call

import boto3

from runzi.automation.scaling.file_utils import download_files, get_output_file_id

# Set up your local config, from environment variables, with some sone defaults
from runzi.automation.scaling.local_config import API_KEY, API_URL, CLUSTER_MODE, S3_URL, WORK_PATH, EnvMode
from runzi.automation.scaling.toshi_api import CreateGeneralTaskArgs, ModelType, SubtaskType, ToshiApi
from runzi.configuration.subduction_inversions import build_subduction_tasks


def run_subduction_inversion(config):
    t0 = dt.datetime.utcnow()

    WORKER_POOL_SIZE = config._worker_pool_size
    USE_API = config._use_api
    TASK_TITLE = config._task_title
    TASK_DESCRIPTION = config._task_description
    GENERAL_TASK_ID = config._general_task_id
    # MOCK_MODE = config._mock_mode
    file_id = config._file_id
    MODEL_TYPE = ModelType[config._model_type]
    SUBTASK_TYPE = SubtaskType[config._subtask_type]

    if CLUSTER_MODE == EnvMode['AWS']:
        work_path = '/WORKING'
    else:
        work_path = WORK_PATH

    headers = {"x-api-key": API_KEY}
    toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

    args = config.get_run_args()
    args_list = []
    for key, value in args.items():
        args_list.append(dict(k=key, v=value))

    file_generator = get_output_file_id(toshi_api, file_id)  # for file by file ID
    rupture_sets = download_files(toshi_api, file_generator, str(work_path), overwrite=False)

    if USE_API:
        # create new task in toshi_api
        gt_args = (
            CreateGeneralTaskArgs(agent_name=os.getlogin(), title=TASK_TITLE, description=TASK_DESCRIPTION)
            .set_argument_list(args_list)
            .set_subtask_type(SUBTASK_TYPE)
            .set_model_type(MODEL_TYPE)
        )

        GENERAL_TASK_ID = toshi_api.general_task.create_task(gt_args)

    if CLUSTER_MODE == EnvMode['AWS']:
        batch_client = boto3.client(
            service_name='batch', region_name='us-east-1', endpoint_url='https://batch.us-east-1.amazonaws.com'
        )

    print("GENERAL_TASK_ID:", GENERAL_TASK_ID)

    scripts = []
    for script_file in build_subduction_tasks(GENERAL_TASK_ID, rupture_sets, args):
        scripts.append(script_file)

    if CLUSTER_MODE == EnvMode['LOCAL']:

        def call_script(script_or_config):
            print("call_script with:", script_or_config)
            check_call(['bash', script_or_config])

        print('task count: ', len(scripts))
        print('worker count: ', WORKER_POOL_SIZE)
        pool = Pool(WORKER_POOL_SIZE)
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

    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())
    print("GENERAL_TASK_ID:", GENERAL_TASK_ID)
