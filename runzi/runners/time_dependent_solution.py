"""
This script produces tasks that modify InversionSolution event rates based on Most Recevnt Events to
produce a Time Dependent Solution
"""

import base64
import datetime as dt
import getpass
import logging
from argparse import ArgumentParser
from pathlib import Path

from runzi.runners.runner_inputs import TimeDependentSolutionInput
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


def run_time_dependent_solution(job_input: TimeDependentSolutionInput) -> str | None:

    source_solution_ids = job_input.solution_ids
    current_years = job_input.current_years
    mre_enums = job_input.mre_enums
    forecast_timespans = job_input.forecast_timespans
    aperiodicities = job_input.aperiodicities
    model_type: ModelType = job_input.model_type
    task_title: str = job_input.title
    task_description: str = job_input.description
    worker_pool_size = job_input.worker_pool_size

    t0 = dt.datetime.now()

    logging.basicConfig(level=logging.INFO)

    loglevel = logging.INFO
    logging.getLogger('py4j.java_gateway').setLevel(loglevel)
    logging.getLogger('nshm_toshi_client.toshi_client_base').setLevel(loglevel)
    logging.getLogger('nshm_toshi_client.toshi_file').setLevel(loglevel)
    logging.getLogger('urllib3').setLevel(loglevel)
    logging.getLogger('botocore').setLevel(loglevel)
    logging.getLogger('git.cmd').setLevel(loglevel)

    # log = logging.getLogger(__name__)

    general_task_id = None

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
            CreateGeneralTaskArgs(agent_name=getpass.getuser(), title=task_title, description=task_description)
            .set_argument_list(args_list)
            .set_subtask_type(subtask_type)
            .set_model_type(model_type)
        )

        general_task_id = toshi_api.general_task.create_task(gt_args)

    print("GENERAL_TASK_ID:", general_task_id)

    tasks = build_tasks(general_task_id, args, subtask_type, model_type, toshi_api)

    toshi_api.general_task.update_subtask_count(general_task_id, len(tasks))

    print('worker count: ', worker_pool_size)

    schedule_tasks(tasks, worker_pool_size)

    print("GENERAL_TASK_ID:", general_task_id)
    print("Done! in %s secs" % (dt.datetime.now() - t0).total_seconds())

    return general_task_id


if __name__ == "__main__":
    parser = ArgumentParser(description="Adjust inversion rates for time dependence.")
    parser.add_argument('filename', help="the input filename")
    args = parser.parse_args()
    with Path(args.filename).open() as input_file:
        job_input = TimeDependentSolutionInput.from_toml(input_file)
    run_time_dependent_solution(job_input)
