import datetime as dt
import getpass
from multiprocessing.dummy import Pool
from pathlib import PurePath
from subprocess import check_call
from typing import TYPE_CHECKING

import boto3

from runzi.automation.scaling.file_utils import download_files, get_output_file_id, get_output_file_ids

# Set up your local config, from environment variables, with some sone defaults
from runzi.automation.scaling.local_config import API_KEY, API_URL, CLUSTER_MODE, S3_URL, WORK_PATH, EnvMode
from runzi.automation.scaling.toshi_api import CreateGeneralTaskArgs, ModelType, SubtaskType, ToshiApi
from runzi.configuration.crustal_inversions import build_crustal_tasks

if TYPE_CHECKING:
    from runzi.runners.inversion_inputs import Config


def run_crustal_inversion(config: 'Config') -> str | None:
    t0 = dt.datetime.now()

    worker_pool_size = config._worker_pool_size
    use_api = config._use_api
    task_title = config._task_title
    task_description = config._task_description
    general_task_id = config._general_task_id
    # MOCK_MODE = config._mock_mode
    file_id = config._file_id  # type: ignore
    model_type = ModelType[config._model_type]  # type: ignore
    subtask_type = SubtaskType[config._subtask_type]  # type: ignore

    work_path: str | PurePath
    if CLUSTER_MODE == EnvMode['AWS']:
        work_path = '/WORKING'
    else:
        work_path = WORK_PATH

    headers = {"x-api-key": API_KEY}
    toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

    args = config.get_run_args()
    args_list = []
    for key, value in args.items():
        val = [str(item) for item in value]
        args_list.append(dict(k=key, v=val))

    # for a file id that is a single rupture set

    # rupture_sets = download_files(toshi_api, file_generator, str(WORK_PATH), overwrite=False)

    # for file_id that is a GT
    # TODO: determine is ID is for a GT or single task and call appropriate get_output...

    try:  # GT ID
        file_generator = get_output_file_ids(toshi_api, file_id)
        rupture_sets = download_files(toshi_api, file_generator, str(work_path), overwrite=False)
        print('GT ID')
    except Exception:  # single file ID
        file_generator = get_output_file_id(toshi_api, file_id)
        rupture_sets = download_files(toshi_api, file_generator, str(work_path), overwrite=False)
        print('file ID')

    # add extra GT meta data gleaned from rupture_sets for TUI
    # TODO
    distances = []
    for rid, rupture_set_info in rupture_sets.items():
        distances.append(rupture_set_info['info']['max_jump_distance'])

    args_list.append(dict(k="max_jump_distances", v=distances))

    if use_api:
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
    for script_file_or_config in build_crustal_tasks(general_task_id, rupture_sets, args, config):
        scripts.append(script_file_or_config)

    toshi_api.general_task.update_subtask_count(general_task_id, len(scripts))
    print(f"GENERAL_TASK_ID:{general_task_id} with {len(scripts)} subtasks")

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

    print(f"general_task_id:{general_task_id} with {len(scripts)} subtasks")
    print("Done! in %s secs" % (dt.datetime.now() - t0).total_seconds())

    return general_task_id
