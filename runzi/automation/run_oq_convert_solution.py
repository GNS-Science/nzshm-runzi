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

from runzi.automation.scaling.toshi_api import ToshiApi, CreateGeneralTaskArgs, SubtaskType
from runzi.automation.scaling.toshi_api.general_task import ModelType
from runzi.configuration.oq_opensha_nrml_convert import build_nrml_tasks
from runzi.automation.scaling.file_utils import download_files, get_output_file_ids, get_output_file_id
from runzi.automation.scaling.schedule_tasks import schedule_tasks
from runzi.automation.scaling.task_utils import get_model_type

from runzi.automation.scaling.local_config import (WORK_PATH, USE_API, JAVA_THREADS,
    API_KEY, API_URL, CLUSTER_MODE, EnvMode )

# If you wish to override something in the main config, do so here ..
WORKER_POOL_SIZE = 4
USE_API = True


def build_tasks(new_gt_id, args, task_type, model_type, toshi_api):
    scripts = []
    for script_file in build_nrml_tasks(new_gt_id, task_type, model_type, args, toshi_api):
        print('scheduling: ', script_file)
        scripts.append(script_file)
    return scripts


def run(scaled_solution_ids, 
        TASK_TITLE: str, TASK_DESCRIPTION: str, WORKER_POOL_SIZE):

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

    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)

    model_type = get_model_type(scaled_solution_ids,toshi_api)

    args = dict(
        rupture_sampling_distance_km = 0.5, # Unit of measure for the rupture sampling: km 
        investigation_time_years = 1.0, # Unit of measure for the `investigation_time`: years 
        input_ids = scaled_solution_ids
    )

    args_list = []
    for key, value in args.items():
        args_list.append(dict(k=key, v=value))

    task_type = SubtaskType.SOLUTION_TO_NRML


    if USE_API:
        #create new task in toshi_api
        gt_args = CreateGeneralTaskArgs(
            agent_name=pwd.getpwuid(os.getuid()).pw_name,
            title=TASK_TITLE,
            description=TASK_DESCRIPTION
            )\
            .set_argument_list(args_list)\
            .set_subtask_type(task_type)\
            .set_model_type(model_type)

        new_gt_id = toshi_api.general_task.create_task(gt_args)

    print("GENERAL_TASK_ID:", new_gt_id)

    tasks = build_tasks(new_gt_id, args, task_type, model_type,toshi_api)

    toshi_api.general_task.update_subtask_count(new_gt_id, len(tasks))

    print('worker count: ', WORKER_POOL_SIZE) 

    schedule_tasks(tasks,WORKER_POOL_SIZE)

    print("GENERAL_TASK_ID:", new_gt_id)
    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())

    return new_gt_id


if __name__ == "__main__":

    # TASK_DESCRIPTION = """Hik Noise Avg"""
    # TASK_TITLE = "Hikurangi Noise Averaged Models"
    # input_ids = [
    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2MzQ4",
    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2MzUy",
    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2MzU2",

    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2MzYw",
    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2MzUw",
    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2MzU0",

    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2MzU4",
    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2MzYy",
    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2MzY0",

    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2MzY4",
    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2Mzcy",
    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2Mzc0",

    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2MzY2",
    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2Mzcw",
    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2Mzc2",

    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2Mzgw",
    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2Mzc5",
    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2Mzgy",

    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2Mzg2",
    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2Mzkw",
    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2Mzg0",

    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2Mzg4",
    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2Mzky",
    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2Mzk2",

    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2Mzk0",
    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2Mzk4",
    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2NDAy",

    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2NDA2",
    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2NDAw",
    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2NDA0"
    # ]

    # TASK_DESCRIPTION = """Puysegur NRMLs"""
    # TASK_TITLE = "Puysegur NRMLs"
    # input_ids = [
    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2NDA5",
    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2NDEw",
    #     ""U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2NDEy"
    # ]

    TASK_DESCRIPTION = """Crustal NRMLs"""
    TASK_TITLE = "Crustal NRMLs"
    input_ids = [
        "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2NDE0",
        "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2NDE4",
        "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2NDIy",
        "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2NDE2",

        "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2NDIw",
        "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2NDI0",
        "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2NDI2",
        "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2NDMw",

        "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2NDM0",
        "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2NDI4",
        "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2NDMy",
        "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2NDM2",

        "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2NDM4",
        "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2NDQy",
        "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2NDQ2",
        "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2NDQw",

        "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2NDQ0",
        "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2NDQ4",
        "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2NDUw",
        "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2NDU0",

        "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2NDU4",
        "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2NDUy",
        "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2NDU2",
        "U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTA2NDYw"
    ]
        
        
    run(input_ids, TASK_TITLE, TASK_DESCRIPTION, WORKER_POOL_SIZE)

