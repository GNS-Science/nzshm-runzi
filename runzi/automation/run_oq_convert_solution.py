#!python3
"""
This script produces tasks in either AWS, PBS or LOCAL that convert an opensha InversionSolution
into source NRML XML files

 -  InversionSolution
 - A GT containing Inversion Solutions

"""
import logging
import pwd
import os
import datetime as dt
from dateutil.tz import tzutc
from subprocess import check_call
from multiprocessing.dummy import Pool

from scaling.toshi_api import ToshiApi, CreateGeneralTaskArgs, SubtaskType
from runzi.configuration.oq_opensha_nrml_convert import build_hazard_tasks
from scaling.file_utils import download_files, get_output_file_ids, get_output_file_id

from scaling.local_config import (WORK_PATH, USE_API, JAVA_THREADS,
    API_KEY, API_URL, CLUSTER_MODE, EnvMode )

def build_tasks(new_gt_id, src_general_tasks, args, task_type, model_type):

    pool = Pool(WORKER_POOL_SIZE)

    scripts = []
    for gt_id in src_general_tasks:
        file_generator = get_output_file_ids(toshi_api, gt_id)
        solutions = download_files(toshi_api, file_generator, str(WORK_PATH), overwrite=False,
            skip_download=(CLUSTER_MODE == EnvMode['AWS']))

        # print(solutions)

        for script_file in build_hazard_tasks(new_gt_id, task_type, model_type, solutions, args):
            print('scheduling: ', script_file)
            scripts.append(script_file)
            assert 0

    if CLUSTER_MODE == EnvMode['LOCAL']:
        print('task count: ', len(scripts))
        pool = Pool(WORKER_POOL_SIZE)
        pool.map(call_script, scripts)
        pool.close()
        pool.join()

    elif CLUSTER_MODE == EnvMode['AWS']:

        batch_client = boto3.client(
            service_name='batch',
            region_name='us-east-1',
            endpoint_url='https://batch.us-east-1.amazonaws.com')

        for script_or_config in scripts:
            print('AWS_CONFIG: ', script_or_config)
            res = batch_client.submit_job(**script_or_config)
            print(res)

    print('worker count: ', WORKER_POOL_SIZE)
    print("GENERAL_TASK_ID:", GENERAL_TASK_ID)
    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())


if __name__ == "__main__":

    t0 = dt.datetime.utcnow()

    logging.basicConfig(level=logging.INFO)

    loglevel = logging.INFO
    logging.getLogger('py4j.java_gateway').setLevel(loglevel)
    logging.getLogger('nshm_toshi_client.toshi_client_base').setLevel(loglevel)
    logging.getLogger('nshm_toshi_client.toshi_file').setLevel(loglevel)
    logging.getLogger('urllib3').setLevel(loglevel)
    logging.getLogger('botocore').setLevel(loglevel)
    logging.getLogger('git.cmd').setLevel(loglevel)

    log = logging.getLogger(__name__)

    GENERAL_TASK_ID = None

    # If you wish to override something in the main config, do so here ..
    WORKER_POOL_SIZE = 1
    HAZARD_MAX_TIME = 15
    USE_API = True

    # #If using API give this task a descriptive setting...
    # #If using API give this task a descriptive setting...
    TASK_TITLE = "A produce some NRML configs from "
    TASK_DESCRIPTION = """first run locally """

    def call_script(script_name):
        print("call_script with:", script_name)
        if CLUSTER_MODE:
            check_call(['qsub', script_name])
        else:
            check_call(['bash', script_name])

    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)

    args = dict(
        rupture_sampling_distance_km = 0.5, # Unit of measure for the rupture sampling: km
        investigation_time_years = 1.0, # Unit of measure for the `investigation_time`: years
    )

    args_list = []
    for key, value in args.items():
        args_list.append(dict(k=key, v=str(value)))

    task_type = SubtaskType.SOLUTION_TO_NRML
    model_type = 'CRUSTAL'

    if USE_API:
        #create new task in toshi_api
        gt_args = CreateGeneralTaskArgs(
            agent_name=pwd.getpwuid(os.getuid()).pw_name,
            title=TASK_TITLE,
            description=TASK_DESCRIPTION
            )\
            .set_argument_list(args_list)\
            .set_subtask_type(task_type.name)\
            .set_model_type(model_type)

        new_gt_id = toshi_api.general_task.create_task(gt_args)

    print("GENERAL_TASK_ID:", new_gt_id)

    general_tasks = ["R2VuZXJhbFRhc2s6MjQ4ODdRTkhH"]
    build_tasks(new_gt_id, general_tasks, args, task_type, model_type)