#!python3
"""
This script produces tasks in either AWS, PBS or LOCAL that run OpenquakeHazard

"""
import logging
import pwd
import os
import datetime as dt
from dateutil.tz import tzutc

from runzi.automation.scaling.toshi_api import ToshiApi, CreateGeneralTaskArgs, SubtaskType, ModelType
from runzi.configuration.oq_hazard import build_hazard_tasks
from runzi.automation.scaling.schedule_tasks import schedule_tasks

from runzi.automation.scaling.local_config import (WORK_PATH, USE_API, JAVA_THREADS,
    API_KEY, API_URL, CLUSTER_MODE, EnvMode )


# from runzi.CONFIG.OQ.archive_ltb import logic_tree_permutations, gt_description
# from runzi.CONFIG.OQ.SLT_v8p0p2_cruonly import logic_tree_permutations, gt_description
# from runzi.CONFIG.OQ.SLT_v9p0p0 import logic_tree_permutations, gt_description
from runzi.CONFIG.OQ.SLT_v8p0p1_test_hdf import logic_tree_permutations, gt_description

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
    logging.getLogger('py4j.java_gateway').setLevel(loglevel)
    logging.getLogger('nshm_toshi_client.toshi_client_base').setLevel(loglevel)
    logging.getLogger('nshm_toshi_client.toshi_file').setLevel(loglevel)
    logging.getLogger('urllib3').setLevel(loglevel)
    logging.getLogger('botocore').setLevel(loglevel)
    logging.getLogger('git.cmd').setLevel(loglevel)
    logging.getLogger('gql.transport').setLevel(logging.WARN)

    log = logging.getLogger(__name__)

    new_gt_id = None

    # If using API give this task a descriptive setting...

    TASK_TITLE = "Openquake Hazard calcs "
    TASK_DESCRIPTION = gt_description

    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)

    era_measures_orig = ['PGA', 'SA(0.1)', 'SA(0.2)', 'SA(0.3)', 'SA(0.4)', 'SA(0.5)', 'SA(0.7)',
        'SA(1.0)', 'SA(1.5)', 'SA(2.0)', 'SA(3.0)', 'SA(4.0)', 'SA(5.0)', 'SA(6.0)','SA(7.5)', 'SA(10.0)']
    era_measures_new = ["SA(0.15)",	"SA(0.25)", "SA(0.35)",	"SA(0.6)", "SA(0.8)", "SA(0.9)",
                    "SA(1.25)", "SA(1.75)", "SA(2.5)", "SA(3.5)", "SA(4.5)"]
    era_measures = era_measures_orig + era_measures_new
    era_levels = [0.0001, 0.0002, 0.0004, 0.0006, 0.0008, 0.001, 0.002, 0.004, 0.006, 0.008,
                    0.01, 0.02, 0.04, 0.06, 0.08, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0,
                    1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8, 3.0, 3.5, 4, 4.5, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]

    vs30s = [525]
    location_lists = [['NZ', 'NZ_0_1_NB_1_1', 'SRWG214']]

    args = dict(
        config_archive_ids = [  # a Toshi File containing zipped configuration, ], #LOCAL'RmlsZToxOA=='],
            "RmlsZToxMjkxNjk4" # GSIM LT v2, no sites
            ],
        # NEW FORM
        # makes better use of python
        logic_tree_permutations =  logic_tree_permutations,

        intensity_specs = [
            { "tag": "fixed", "measures": era_measures, "levels": era_levels},
        ],
        vs30s = vs30s,
        location_lists = location_lists,
        disagg_confs = [{'enabled': False, 'config': {}},
            # {'enabled': True, 'config': {}}
        ],
        rupture_mesh_spacings = [4], #1,2,3,4,5,6,7,8,9],
        ps_grid_spacings = [30], #km 
    )

    args_list = []
    for key, value in args.items():
        args_list.append(dict(k=key, v=value))

    task_type = SubtaskType.OPENQUAKE_HAZARD
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
