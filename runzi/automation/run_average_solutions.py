from operator import mod
import pwd
import logging
import os
import datetime as dt
from pyexpat import model
from statistics import mode

from runzi.configuration.average_inversion_solutions import build_average_tasks
from runzi.automation.scaling.schedule_tasks import schedule_tasks
from runzi.automation.scaling.toshi_api import ToshiApi, CreateGeneralTaskArgs, SubtaskType
from runzi.automation.scaling.toshi_api.general_task import ModelType
from runzi.automation.scaling.task_utils import get_model_type



from runzi.automation.scaling.local_config import (WORK_PATH, USE_API,
    API_KEY, API_URL, CLUSTER_MODE, EnvMode )

# If you wish to override something in the main config, do so here ..
#WORKER_POOL_SIZE = 2 
WORKER_POOL_SIZE = None
USE_API = True

def build_tasks(new_gt_id, args, task_type, model_type, toshi_api):
    scripts = []
    for script_file in build_average_tasks(new_gt_id, task_type, model_type, args, toshi_api):
        print('scheduling: ', script_file)
        scripts.append(script_file)
    return scripts

def run(source_solution_groups, TASK_TITLE, TASK_DESCRIPTION , WORKER_POOL_SIZE):

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

    model_type = None
    for source_solution_ids in source_solution_groups:
        new_model_type = get_model_type(source_solution_ids,toshi_api)
        if (not model_type):
            model_type = new_model_type
        else:
            if new_model_type is model_type:
                continue
            else:
                raise Exception(f'model types are not all the same for source solution groups {source_solution_groups}')


    subtask_type = SubtaskType.AGGREGATE_SOLUTION

    args = dict(
        source_solution_groups = source_solution_groups
    )

    args_list = []
    for key, value in args.items():
        args_list.append(dict(k=key, v=value))

    if USE_API:
        #create new task in toshi_api
        gt_args = CreateGeneralTaskArgs(
            agent_name=pwd.getpwuid(os.getuid()).pw_name,
            title=TASK_TITLE,
            description=TASK_DESCRIPTION
            )\
            .set_argument_list(args_list)\
            .set_subtask_type(subtask_type)\
            .set_model_type(model_type) 

        GENERAL_TASK_ID = toshi_api.general_task.create_task(gt_args)

    print("GENERAL_TASK_ID:", GENERAL_TASK_ID)

    tasks = build_tasks(GENERAL_TASK_ID, args, subtask_type, model_type, toshi_api)

    toshi_api.general_task.update_subtask_count(GENERAL_TASK_ID, len(tasks))

    print('worker count: ', WORKER_POOL_SIZE)

    schedule_tasks(tasks,WORKER_POOL_SIZE)

    print("GENERAL_TASK_ID:", GENERAL_TASK_ID)
    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())

    return GENERAL_TASK_ID



if __name__ == "__main__":

    TASK_DESCRIPTION = 'TEST_RUP_SETS'

    if TASK_DESCRIPTION == 'TEST':
        TASK_TITLE = "TEST averaging"
        model_type = ModelType.SUBDUCTION
        source_solution_groups = [
            ["SW52ZXJzaW9uU29sdXRpb246MTAwNDk5","SW52ZXJzaW9uU29sdXRpb246MTAwNTA3","SW52ZXJzaW9uU29sdXRpb246MTAwNTEw","SW52ZXJzaW9uU29sdXRpb246MTAwNTEz"],
            ["SW52ZXJzaW9uU29sdXRpb246MTAwNTE1", "SW52ZXJzaW9uU29sdXRpb246MTAwNTE2", "SW52ZXJzaW9uU29sdXRpb246MTAwNTE3", "SW52ZXJzaW9uU29sdXRpb246MTAwNTIw"],

        ]
    if TASK_DESCRIPTION == 'TEST_PRED':
        TASK_TITLE = "TEST averaging with predecessors"
        model_type = ModelType.SUBDUCTION
        source_solution_groups = [
            ["U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAwODYz","U2NhbGVkSW52ZXJzaW9uU29sdXRpb246MTAwODYz"]
        ]

    if TASK_DESCRIPTION == 'TEST_RUP_SETS':
        TASK_TITLE = "TEST averaging with retrieving rupture sets"
        model_type = ModelType.SUBDUCTION
        source_solution_groups = [
            ["SW52ZXJzaW9uU29sdXRpb246MTAxMTA4","SW52ZXJzaW9uU29sdXRpb246MTAxMTEx"]
        ]
    if TASK_DESCRIPTION == 'TEST_RUP_SETS_DIFF':
        TASK_TITLE = "TEST averaging with retrieving rupture sets (should fail, they are not consistent)"
        model_type = ModelType.SUBDUCTION
        source_solution_groups = [
            # ["SW52ZXJzaW9uU29sdXRpb246MTAxMTA4","SW52ZXJzaW9uU29sdXRpb246MTAxMTE2"]
            ["SW52ZXJzaW9uU29sdXRpb246MTAxMTA4","SW52ZXJzaW9uU29sdXRpb246MTAxMTEx"],
            ["SW52ZXJzaW9uU29sdXRpb246MTAxMTE2","SW52ZXJzaW9uU29sdXRpb246MTAxMTE2"]
        ]


    run(source_solution_groups, TASK_TITLE, TASK_DESCRIPTION , WORKER_POOL_SIZE)
