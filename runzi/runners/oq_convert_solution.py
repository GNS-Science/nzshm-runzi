"""This module provides the runner function to convert an opensha InversionSolution into source NRML XML files."""

import base64
import datetime as dt
import getpass
import logging
from argparse import ArgumentParser
from typing import Optional

from runzi.automation.scaling.file_utils import get_output_file_ids
from runzi.automation.scaling.local_config import API_KEY, API_URL, USE_API
from runzi.automation.scaling.schedule_tasks import schedule_tasks
from runzi.automation.scaling.task_utils import get_model_type
from runzi.automation.scaling.toshi_api import CreateGeneralTaskArgs, ModelType, SubtaskType, ToshiApi

try:
    from runzi.configuration.oq_opensha_nrml_convert import build_nrml_tasks
except ImportError:
    print("openquake not installed, not importing")


def build_tasks(
    new_gt_id: str | None, args: dict, task_type: SubtaskType, model_type: ModelType, toshi_api: ToshiApi
) -> list:
    scripts = []
    for script_file in build_nrml_tasks(new_gt_id, task_type, model_type, args, toshi_api):
        print('scheduling: ', script_file)
        scripts.append(script_file)
    return scripts


def run_oq_convert_solution(
    ids: list[str],
    title: str,
    description: str,
    num_workers: Optional[int] = None,
) -> str | None:
    """Launch jobs to convert OpenSHA inversion solutions to OpenQuake source input files.

    Args:
        ids: List toshi IDs of objects to convert. Can be individual InversionSolutions or GeneralTask.
        title: Title for the task.
        description: A description of the task.
        num_workers: The number of processes to run in parallel.

    Returns:
        general task ID if using toshi API
    """

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
    for source_solution_id in ids:
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
            CreateGeneralTaskArgs(agent_name=getpass.getuser(), title=title, description=description)
            .set_argument_list(args_list)
            .set_subtask_type(task_type)
            .set_model_type(model_type)
        )

        new_gt_id = toshi_api.general_task.create_task(gt_args)

    print("GENERAL_TASK_ID:", new_gt_id)

    tasks = build_tasks(new_gt_id, args, task_type, model_type, toshi_api)

    if USE_API:
        toshi_api.general_task.update_subtask_count(new_gt_id, len(tasks))

    print('worker count: ', num_workers)

    schedule_tasks(tasks, num_workers)

    print("GENERAL_TASK_ID:", new_gt_id)
    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())

    return new_gt_id


def parse_args():
    parser = ArgumentParser(description="convert OpenSHA inversion solutions to OQ source files.")
    parser.add_argument("title")
    parser.add_argument("description")
    parser.add_argument(
        "ids",
        nargs='*',
        help="IDs of objects to convert (whitespace seperated). Can be a GeneralTask or InversionSolution type",
    )
    parser.add_argument("-n", "--num-workers", type=int, default=1, help="number of parallel workers")
    args = parser.parse_args()
    return vars(args)


if __name__ == "__main__":
    run_oq_convert_solution(**parse_args())
