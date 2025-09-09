import datetime as dt
import getpass
import logging
from argparse import ArgumentParser
from pathlib import Path

from runzi.automation.scaling.local_config import API_KEY, API_URL, USE_API
from runzi.automation.scaling.schedule_tasks import schedule_tasks
from runzi.automation.scaling.task_utils import get_model_type
from runzi.automation.scaling.toshi_api import CreateGeneralTaskArgs, SubtaskType, ToshiApi
from runzi.configuration.average_inversion_solutions import build_average_tasks
from runzi.runners.runner_inputs import InputBase


class AverageSolutionsInput(InputBase):
    """Input for averaging solutions."""

    solution_groups: list[list[str]]


def build_tasks(new_gt_id, args, task_type, model_type, toshi_api):
    scripts = []
    for script_file in build_average_tasks(new_gt_id, task_type, model_type, args, toshi_api):
        print('scheduling: ', script_file)
        scripts.append(script_file)
    return scripts


def run_average_solutions(job_input: AverageSolutionsInput) -> str | None:

    source_solution_groups = job_input.solution_groups
    task_title = job_input.title
    task_description = job_input.description
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

    args = dict(source_solution_groups=source_solution_groups)

    args_list = []
    for key, value in args.items():
        args_list.append(dict(k=key, v=value))

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

    parser = ArgumentParser(description="Create new solutions that are the mean of two or more inverions.")
    parser.add_argument('filename', help="the input filename")
    args = parser.parse_args()
    with Path(args.filename).open() as input_file:
        job_input = AverageSolutionsInput.from_toml(input_file)
    run_average_solutions(job_input)
