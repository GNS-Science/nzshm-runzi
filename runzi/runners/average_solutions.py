"""This module provides the runner function for averaging the rupture rates from multiple inversions."""

import datetime as dt
import getpass
from argparse import ArgumentParser
from pathlib import Path

from runzi.automation.scaling.local_config import API_KEY, API_URL, USE_API, WORKER_POOL_SIZE
from runzi.automation.scaling.schedule_tasks import schedule_tasks
from runzi.automation.scaling.task_utils import get_model_type
from runzi.automation.scaling.toshi_api import CreateGeneralTaskArgs, SubtaskType, ToshiApi
from runzi.configuration.arguments import SystemArgs
from runzi.configuration.average_inversion_solutions import build_average_tasks
from runzi.runners.runner_inputs import AverageSolutionsInput


def build_tasks(user_args: AverageSolutionsInput, system_args: SystemArgs):
    scripts = []
    for script_file in build_average_tasks(user_args, system_args):
        print('scheduling: ', script_file)
        scripts.append(script_file)
    return scripts


def run_average_solutions(job_input: AverageSolutionsInput) -> str | None:
    """Launch jobs to calculate averaged inversion solutions by taking mean rates.

    Args:
        job_input: input arguments

    Returns:
        general task ID if using toshi API
    """
    source_solution_groups = job_input.solution_groups
    task_title = job_input.title
    task_description = job_input.description

    t0 = dt.datetime.now()

    general_task_id = None

    headers = {"x-api-key": API_KEY}
    toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)

    model_type = None
    for source_solution_ids in source_solution_groups:
        new_model_type = get_model_type(source_solution_ids, toshi_api)
        if not model_type:
            model_type = new_model_type
        else:
            if new_model_type is model_type:
                continue
            else:
                raise Exception(f'model types are not all the same for source solution groups {source_solution_groups}')

    subtask_type = SubtaskType.AGGREGATE_SOLUTION
    system_args = SystemArgs(general_task_id=general_task_id, use_api=USE_API)
    if USE_API:
        args_list = dict(k='source_solution_groups', v=str(source_solution_ids))
        # create new task in toshi_api
        gt_args = (
            CreateGeneralTaskArgs(agent_name=getpass.getuser(), title=task_title, description=task_description)
            .set_argument_list(args_list)
            .set_subtask_type(subtask_type)
            .set_model_type(model_type)
        )
        general_task_id = toshi_api.general_task.create_task(gt_args)

    print("GENERAL_TASK_ID:", general_task_id)
    tasks = build_tasks(job_input, system_args)
    if USE_API:
        toshi_api.general_task.update_subtask_count(general_task_id, len(tasks))
    print('worker count: ', WORKER_POOL_SIZE)
    schedule_tasks(tasks, WORKER_POOL_SIZE)
    print("GENERAL_TASK_ID:", general_task_id)
    print("Done! in %s secs" % (dt.datetime.now() - t0).total_seconds())

    return general_task_id


if __name__ == "__main__":

    parser = ArgumentParser(description="Create new solutions that are the mean of two or more inverions.")
    parser.add_argument('filename', help="the input filename")
    args = parser.parse_args()
    with Path(args.filename).open() as input_file:
        job_input = AverageSolutionsInput.from_toml_file(input_file)
    run_average_solutions(job_input)
