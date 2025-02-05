#!python3
"""
This script produces tasks in either AWS, PBS or LOCAL that convert an opensha InversionSolution
into source NRML XML files

 -  InversionSolution
 - A GT containing Inversion Solutions

"""
import base64
import datetime as dt
import logging
import os
import pwd

from runzi.automation.scaling.file_utils import get_output_file_ids
from runzi.automation.scaling.local_config import API_KEY, API_URL, USE_API
from runzi.automation.scaling.schedule_tasks import schedule_tasks
from runzi.automation.scaling.task_utils import get_model_type
from runzi.automation.scaling.toshi_api import CreateGeneralTaskArgs, SubtaskType, ToshiApi
from runzi.configuration.oq_opensha_nrml_convert import build_nrml_tasks

# If you wish to override something in the main config, do so here ..
WORKER_POOL_SIZE = 27
# USE_API = True


def build_tasks(new_gt_id, args, task_type, model_type, toshi_api):
    scripts = []
    for script_file in build_nrml_tasks(new_gt_id, task_type, model_type, args, toshi_api):
        print('scheduling: ', script_file)
        scripts.append(script_file)
    return scripts


def run(scaled_solution_ids, TASK_TITLE: str, TASK_DESCRIPTION: str, WORKER_POOL_SIZE):

    t0 = dt.datetime.utcnow()

    logging.basicConfig(level=logging.INFO)

    loglevel = logging.INFO
    logging.getLogger('py4j.java_gateway').setLevel(loglevel)
    logging.getLogger('nshm_toshi_client.toshi_client_base').setLevel(loglevel)
    logging.getLogger('nshm_toshi_client.toshi_file').setLevel(loglevel)
    logging.getLogger('urllib3').setLevel(loglevel)
    logging.getLogger('botocore').setLevel(loglevel)
    logging.getLogger('git.cmd').setLevel(loglevel)

    new_gt_id = None

    headers = {"x-api-key": API_KEY}
    toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)

    # if a GT id has been provided, unpack to get individual solution ids
    source_solution_ids_list = []
    for source_solution_id in scaled_solution_ids:
        if 'GeneralTask' in str(base64.b64decode(source_solution_id)):
            source_solution_ids_list += [out['id'] for out in get_output_file_ids(toshi_api, source_solution_id)]
        else:
            source_solution_ids_list += [source_solution_id]

    model_type = get_model_type(source_solution_ids_list, toshi_api)

    args = dict(
        rupture_sampling_distance_km=0.5,  # Unit of measure for the rupture sampling: km
        investigation_time_years=1.0,  # Unit of measure for the `investigation_time`: years
        input_ids=source_solution_ids_list,
    )

    args_list = []
    for key, value in args.items():
        args_list.append(dict(k=key, v=value))

    task_type = SubtaskType.SOLUTION_TO_NRML

    if USE_API:
        # create new task in toshi_api
        gt_args = (
            CreateGeneralTaskArgs(
                agent_name=pwd.getpwuid(os.getuid()).pw_name, title=TASK_TITLE, description=TASK_DESCRIPTION
            )
            .set_argument_list(args_list)
            .set_subtask_type(task_type)
            .set_model_type(model_type)
        )

        new_gt_id = toshi_api.general_task.create_task(gt_args)

    print("GENERAL_TASK_ID:", new_gt_id)

    tasks = build_tasks(new_gt_id, args, task_type, model_type, toshi_api)

    if USE_API:
        toshi_api.general_task.update_subtask_count(new_gt_id, len(tasks))

    print('worker count: ', WORKER_POOL_SIZE)

    schedule_tasks(tasks, WORKER_POOL_SIZE)

    print("GENERAL_TASK_ID:", new_gt_id)
    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())

    return new_gt_id


if __name__ == "__main__":

    TASK_DESCRIPTION = """Crustal NRMLs"""
    TASK_TITLE = " geodetic. Time Dependent. From R2VuZXJhbFRhc2s6NjUzOTc5MA=="
    input_ids = [
        "R2VuZXJhbFRhc2s6NjUzOTc5MA==",
    ]

    run(input_ids, TASK_TITLE, TASK_DESCRIPTION, WORKER_POOL_SIZE)
