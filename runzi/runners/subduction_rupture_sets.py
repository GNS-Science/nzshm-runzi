"""This module provides the runner function to build subduction rupture sets."""

import datetime as dt
import getpass
from argparse import ArgumentParser
from multiprocessing.dummy import Pool
from pathlib import Path
import logging
from subprocess import check_call

from runzi.execute.arguments import SystemArgs, ArgSweeper


# Set up your local config, from environment variables, with some sone defaults
from runzi.automation.scaling.local_config import (
    API_KEY,
    API_URL,
    CLUSTER_MODE,
    JAVA_THREADS,
    S3_URL,
    USE_API,
)
from runzi.automation.scaling.toshi_api import CreateGeneralTaskArgs, ModelType, SubtaskType, ToshiApi
from runzi.configuration.subduction_rupture_sets import build_tasks
from runzi.execute.subduction_rupture_set_builder_task import SubductionRuptureSetArgs

JVM_HEAP_MAX = 12
JVM_HEAP_START = 2

INITIAL_GATEWAY_PORT = 26533  # set this to ensure that concurrent scheduled tasks won't clash
MAX_JOB_TIME_SECS = 60 * 30  # Change this soon


def run_subduction_rupture_sets(job_input: ArgSweeper) -> str | None:
    """Launch jobs to build subduction rupture sets.

    Args:
        job_input: input arguments

    Returns:
        general task ID if using toshi API
    """

    t0 = dt.datetime.now()

    general_task_id = None
    headers = {"x-api-key": API_KEY}
    toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

    task_title = job_input.title
    task_description = job_input.description
    worker_pool_size = job_input.worker_pool_size  # TODO: make this an env var. Consistent with inversion?

    args_list = []
    for key, value in job_input.model_dump().items():
        val = [str(item) for item in value]
        args_list.append(dict(k=key, v=val))

    if USE_API:

        subtask_type = SubtaskType.RUPTURE_SET
        model_type = ModelType.SUBDUCTION
        # create new task in toshi_api
        gt_args = (
            CreateGeneralTaskArgs(agent_name=getpass.getuser(), title=task_title, description=task_description)
            .set_argument_list(args_list)
            .set_subtask_type(subtask_type)
            .set_model_type(model_type)
        )

        general_task_id = toshi_api.general_task.create_task(gt_args)

    print("GENERAL_TASK_ID:", general_task_id)

    pool = Pool(worker_pool_size)

    scripts = []
    for script_file in build_tasks(general_task_id, job_input):
        scripts.append(script_file)

    def call_script(script_name):
        print("call_script with:", script_name)
        if CLUSTER_MODE:
            check_call(['qsub', script_name])
        else:
            check_call(['bash', script_name])

    print('task count: ', len(scripts))
    print('worker count: ', worker_pool_size)

    pool.map(call_script, scripts)
    pool.close()
    pool.join()

    print("Done! in %s secs" % (dt.datetime.now() - t0).total_seconds())

    return general_task_id


if __name__ == "__main__":
    parser = ArgumentParser(description="Create subduction rupture sets.")
    parser.add_argument('filename', help="the input filename")
    args = parser.parse_args()
    with Path(args.filename).open() as input_file:
        job_input = SubductionRuptureSetArgs.from_toml_file(input_file)
    run_subduction_rupture_sets(job_input)
