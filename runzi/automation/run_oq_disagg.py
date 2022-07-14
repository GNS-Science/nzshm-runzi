#!python3
"""
This script produces disagg tasks in either AWS, PBS or LOCAL that run OpenquakeHazard in disagg mode.

"""
import logging
import pwd
import os
import datetime as dt

from runzi.automation.scaling.toshi_api import ToshiApi, CreateGeneralTaskArgs, SubtaskType, ModelType
from runzi.configuration.oq_disagg import build_hazard_tasks
from runzi.automation.scaling.schedule_tasks import schedule_tasks

from runzi.automation.scaling.local_config import (WORK_PATH, USE_API, JAVA_THREADS,
    API_KEY, API_URL, CLUSTER_MODE, EnvMode )

from runzi.CONFIG.OQ.poly_sens_nopolygon import logic_tree_permutations, gt_description

# If you wish to override something in the main config, do so here ..
WORKER_POOL_SIZE = 1

def build_tasks(new_gt_id, args, task_type, model_type):

    scripts = []
    for script_file in build_hazard_tasks(new_gt_id, task_type, model_type, args):
        print('scheduling: ', script_file)
        scripts.append(script_file)

    return scripts

if __name__ == "__main__":

    t0 = dt.datetime.utcnow()

    logging.basicConfig(level=logging.INFO)

    loglevel = logging.INFO
    # logging.getLogger('nshm_toshi_client.toshi_client_base').setLevel(loglevel)
    # logging.getLogger('nshm_toshi_client.toshi_file').setLevel(loglevel)
    # logging.getLogger('urllib3').setLevel(loglevel)
    # logging.getLogger('botocore').setLevel(loglevel)
    logging.getLogger('gql.transport').setLevel(logging.WARN)
    log = logging.getLogger(__name__)

    new_gt_id = None

    # If using API give this task a descriptive setting...

    TASK_TITLE = "Openquake Disagg calcs "
    TASK_DESCRIPTION = gt_description

    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)

    args = dict(
        disagg_configs =  disagg_configs,
        rupture_mesh_spacings = [5], #1,2,3,4,5,6,7,8,9],
        ps_grid_spacings = [30], #km 
    )

    args_list = []
    for key, value in args.items():
        args_list.append(dict(k=key, v=value))

    task_type = SubtaskType.OPENQUAKE_HAZARD #TODO: create a new task type
    model_type = ModelType.COMPOSITE

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

    tasks = build_tasks(new_gt_id, args, task_type, model_type)

    # toshi_api.general_task.update_subtask_count(new_gt_id, len(tasks))
    print('worker count: ', WORKER_POOL_SIZE)
    print(f'tasks to schedule: {len(tasks)}')

    schedule_tasks(tasks, WORKER_POOL_SIZE)

    print("GENERAL_TASK_ID:", new_gt_id)
    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())
