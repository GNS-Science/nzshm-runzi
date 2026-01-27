import datetime as dt
import getpass
from multiprocessing.dummy import Pool
from subprocess import check_call

import boto3

# Set up your local config, from environment variables, with some sone defaults
from runzi.automation.scaling.local_config import (
    API_KEY,
    API_URL,
    CLUSTER_MODE,
    S3_URL,
    USE_API,
    WORKER_POOL_SIZE,
    EnvMode,
)
from runzi.automation.scaling.toshi_api import CreateGeneralTaskArgs, SubtaskType, ToshiApi
from runzi.configuration.inversions import build_inversion_tasks
from runzi.execute.arguments import SystemArgs
from runzi.runners.inversion_inputs import InversionArgs


def run_inversion(inversion_args: InversionArgs) -> str | None:
    t0 = dt.datetime.now()
    system_args = SystemArgs()

    worker_pool_size = WORKER_POOL_SIZE
    if inversion_args.general.subtask_type is not SubtaskType.INVERSION:
        raise ValueError("subtask type must be INVERSION")
    # if inversion_args.general.model_type is ModelType.SUBDUCTION:
    #     build_tasks = build_subduction_tasks
    # elif inversion_args.general.model_type is ModelType.CRUSTAL:
    #     build_tasks = build_crustal_tasks
    # if :
    #     raise ValueError("model type must be SUBDUCTION or CRUSTAL")

    headers = {"x-api-key": API_KEY}
    toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

    args_list = []
    for key, value in inversion_args.get_run_args().items():
        val = [str(item) for item in value]
        args_list.append(dict(k=key, v=val))

    general_task_id: str | None = None
    if USE_API:
        # create new task in toshi_api
        gt_args = (
            CreateGeneralTaskArgs(
                agent_name=getpass.getuser(),
                title=inversion_args.title,
                description=inversion_args.description,
            )
            .set_argument_list(args_list)
            .set_subtask_type(inversion_args.general.subtask_type)
            .set_model_type(inversion_args.general.model_type)
        )

        general_task_id = toshi_api.general_task.create_task(gt_args)

    if CLUSTER_MODE == EnvMode['AWS']:
        batch_client = boto3.client(
            service_name='batch', region_name='us-east-1', endpoint_url='https://batch.us-east-1.amazonaws.com'
        )

    print("GENERAL_TASK_ID:", general_task_id)
    system_args.general_task_id = general_task_id

    scripts = []
    for script_file in build_inversion_tasks(inversion_args, system_args):
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
            check_call(['qsub', script_or_config])  # type: ignore

    print("Done! in %s secs" % (dt.datetime.now() - t0).total_seconds())

    return general_task_id
