"""
This script produces tasks that modify InversionSolution event rates based on Most Recevnt Events to
produce a Time Dependent Solution
"""

import base64
import datetime as dt
import logging
import os

from runzi.automation.scaling.file_utils import get_output_file_ids
from runzi.automation.scaling.local_config import API_KEY, API_URL, USE_API
from runzi.automation.scaling.schedule_tasks import schedule_tasks
from runzi.automation.scaling.toshi_api import CreateGeneralTaskArgs, SubtaskType, ToshiApi
from runzi.automation.scaling.toshi_api.general_task import ModelType
from runzi.configuration.time_dependent_inversion_solution import build_time_dependent_tasks


def build_tasks(new_gt_id, args, task_type, model_type, toshi_api):
    scripts = []
    for script_file in build_time_dependent_tasks(new_gt_id, task_type, model_type, args, toshi_api):
        print('scheduling: ', script_file)
        scripts.append(script_file)
    return scripts


def run(
    source_solution_ids,
    current_years,
    mre_enums,
    forecast_timespans,
    aperiodicities,
    model_type: ModelType,
    TASK_TITLE: str,
    TASK_DESCRIPTION: str,
    WORKER_POOL_SIZE,
):
    t0 = dt.datetime.utcnow()

    logging.basicConfig(level=logging.INFO)

    loglevel = logging.INFO
    logging.getLogger('py4j.java_gateway').setLevel(loglevel)
    logging.getLogger('nshm_toshi_client.toshi_client_base').setLevel(loglevel)
    logging.getLogger('nshm_toshi_client.toshi_file').setLevel(loglevel)
    logging.getLogger('urllib3').setLevel(loglevel)
    logging.getLogger('botocore').setLevel(loglevel)
    logging.getLogger('git.cmd').setLevel(loglevel)

    # log = logging.getLogger(__name__)

    GENERAL_TASK_ID = None

    headers = {"x-api-key": API_KEY}
    toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)

    # if a GT id has been provided, unpack to get individual solution ids
    source_solution_ids_list = []
    for source_solution_id in source_solution_ids:
        if 'GeneralTask' in str(base64.b64decode(source_solution_id)):
            source_solution_ids_list += [out['id'] for out in get_output_file_ids(toshi_api, source_solution_id)]
        else:
            source_solution_ids_list += [source_solution_id]

    subtask_type = SubtaskType.TIME_DEPENDENT_SOLUTION

    args = dict(
        current_years=current_years,
        mre_enums=mre_enums,
        aperiodicities=aperiodicities,
        forecast_timespans=forecast_timespans,
        source_solution_ids=source_solution_ids_list,
    )

    args_list = []
    for key, value in args.items():
        args_list.append(dict(k=key, v=value))
    print(args_list)

    if USE_API:
        # create new task in toshi_api
        gt_args = (
            CreateGeneralTaskArgs(agent_name=os.getlogin(), title=TASK_TITLE, description=TASK_DESCRIPTION)
            .set_argument_list(args_list)
            .set_subtask_type(subtask_type)
            .set_model_type(model_type)
        )

        GENERAL_TASK_ID = toshi_api.general_task.create_task(gt_args)

    print("GENERAL_TASK_ID:", GENERAL_TASK_ID)

    tasks = build_tasks(GENERAL_TASK_ID, args, subtask_type, model_type, toshi_api)

    toshi_api.general_task.update_subtask_count(GENERAL_TASK_ID, len(tasks))

    print('worker count: ', WORKER_POOL_SIZE)

    schedule_tasks(tasks, WORKER_POOL_SIZE)

    print("GENERAL_TASK_ID:", GENERAL_TASK_ID)
    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())

    return GENERAL_TASK_ID


if __name__ == "__main__":

    # If you wish to override something in the main config, do so here ..
    WORKER_POOL_SIZE = 9
    # USE_API =

    # #If using API give this task a descriptive setting...
    TASK_DESCRIPTION = """Crustal. Geodetic. TD. From LTB89. Final """

    TASK_TITLE = "Crustal. Geodetic. TD. From LTB98. 100yr. NZ-SHM22 aperiodicity"
    model_type = ModelType.CRUSTAL
    source_solution_ids = [
        "R2VuZXJhbFRhc2s6NjUzOTY1OQ==",
    ]
    current_years = [2022]
    mre_enums = ["CFM_1_1"]
    forecast_timespans = [100]
    aperiodicities = ["NZSHM22"]

    run(
        source_solution_ids,
        current_years,
        mre_enums,
        forecast_timespans,
        aperiodicities,
        model_type,
        TASK_TITLE,
        TASK_DESCRIPTION,
        WORKER_POOL_SIZE,
    )
