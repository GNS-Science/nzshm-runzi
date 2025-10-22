"""This module provides the runner function to convert an opensha InversionSolution into source NRML XML files."""

import datetime as dt
import getpass
import logging
from argparse import ArgumentParser
from pathlib import Path

from runzi.automation.scaling.local_config import API_KEY, API_URL, USE_API, WORKER_POOL_SIZE
from runzi.automation.scaling.schedule_tasks import schedule_tasks
from runzi.automation.scaling.toshi_api import CreateGeneralTaskArgs, SubtaskType, ToshiApi
from runzi.runners.runner_inputs import OQOpenSHAConvertArgs, SystemArgs

try:
    from runzi.configuration.oq_opensha_nrml_convert import build_nrml_tasks
except ImportError:
    print("openquake not installed, not importing")


def run_oq_convert_solution(user_args: OQOpenSHAConvertArgs) -> str | None:
    """Launch jobs to convert OpenSHA inversion solutions to OpenQuake source input files.

    Args:
        user_args: input arguments

    Returns:
        general task ID if using toshi API
    """

    t0 = dt.datetime.now()

    logging.basicConfig(level=logging.INFO)

    loglevel = logging.INFO
    logging.getLogger('py4j.java_gateway').setLevel(loglevel)
    logging.getLogger('nshm_toshi_client.toshi_client_base').setLevel(loglevel)
    logging.getLogger('nshm_toshi_client.toshi_file').setLevel(loglevel)
    logging.getLogger('urllib3').setLevel(loglevel)
    logging.getLogger('botocore').setLevel(loglevel)
    logging.getLogger('git.cmd').setLevel(loglevel)

    # TODO: this is done so often and handled differently for lists and non-lists, should use a
    # function to do it the same every time
    args_list = []
    for key, value in user_args.get_run_args().items():
        val = [str(value)]
        args_list.append(dict(k=key, v=val))

    general_task_id = None
    if USE_API:
        headers = {"x-api-key": API_KEY}
        toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)
        gt_args = (
            CreateGeneralTaskArgs(
                agent_name=getpass.getuser(), title=user_args.title, description=user_args.description
            )
            .set_argument_list(args_list)
            .set_subtask_type(SubtaskType.SOLUTION_TO_NRML)
            .set_model_type(user_args.task.model_type)
        )
        general_task_id = toshi_api.general_task.create_task(gt_args)

    system_args = SystemArgs(general_task_id=general_task_id, use_api=USE_API)

    tasks = []
    for script_file in build_nrml_tasks(user_args, system_args):
        print('scheduling: ', script_file)
        tasks.append(script_file)

    if USE_API:
        toshi_api.general_task.update_subtask_count(general_task_id, len(tasks))

    print('worker count: ', WORKER_POOL_SIZE)

    # TODO: use this in all runners
    schedule_tasks(tasks, WORKER_POOL_SIZE)

    print("GENERAL_TASK_ID:", general_task_id)
    print("Done! in %s secs" % (dt.datetime.now() - t0).total_seconds())

    return general_task_id


if __name__ == "__main__":

    parser = ArgumentParser(description="convert OpenSHA inversion solutions to OQ source files.")
    parser.add_argument('filename', help="the input filename")
    args = parser.parse_args()
    with Path(args.filename).open() as input_file:
        job_input = OQOpenSHAConvertArgs.from_toml_file(input_file)
    run_oq_convert_solution(job_input)
