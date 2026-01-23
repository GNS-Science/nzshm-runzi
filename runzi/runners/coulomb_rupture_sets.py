"""This module provides the runner function for creating Coulomb rupture sets."""

import datetime as dt
import getpass
import logging
from argparse import ArgumentParser
from multiprocessing.dummy import Pool
from pathlib import Path
from subprocess import check_call
from typing import TYPE_CHECKING

from runzi.automation.scaling.local_config import API_KEY, API_URL, CLUSTER_MODE, S3_URL, USE_API, WORKER_POOL_SIZE
from runzi.automation.scaling.toshi_api import CreateGeneralTaskArgs, ModelType, SubtaskType, ToshiApi
from runzi.execute.arguments import SystemArgs, ArgSweeper
from runzi.configuration.coulomb_rupture_sets import build_tasks

logging.basicConfig(level=logging.INFO)


def run_coulomb_rupture_sets(job_args: ArgSweeper) -> str | None:
    """Launch jobs to build Coulomb (crustal) rupture sets.

    Args:
        job_input: input arguments including swept args.

    Returns:
        general task ID if using toshi API or None.
    """
    t0 = dt.datetime.now()
    system_args = SystemArgs()

    logging.basicConfig(level=logging.INFO)

    loglevel = logging.INFO
    logging.getLogger('py4j.java_gateway').setLevel(loglevel)
    logging.getLogger('nshm_toshi_client.toshi_client_base').setLevel(loglevel)
    logging.getLogger('nshm_toshi_client.toshi_file').setLevel(loglevel)
    logging.getLogger('urllib3').setLevel(loglevel)
    logging.getLogger('botocore').setLevel(loglevel)
    logging.getLogger('git.cmd').setLevel(loglevel)

    # USE_API = False
    general_task_id = None

    # TODO: this can be a reused function (or a method on ArgSweeper?)
    unswepped_args = {k: [str(v),] for k,v in job_args.prototype.get_run_args().items()}
    swepted_args = {k: [str(item) for item in v] for k, v in job_args.swept_args.items()}
    all_args = unswepped_args | swepted_args
    args_list = [dict(k=key, v=value) for key, value in all_args.items()]

    if USE_API:
        # create new task in toshi_api
        headers = {"x-api-key": API_KEY}
        toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

        gt_args = (
            CreateGeneralTaskArgs(agent_name=getpass.getuser(), title=job_args.title, description=job_args.description)
            .set_argument_list(args_list)
            .set_subtask_type(SubtaskType['RUPTURE_SET'])
            .set_model_type(ModelType['CRUSTAL'])
        )
        general_task_id = toshi_api.general_task.create_task(gt_args)

    print("GENERAL_TASK_ID:", general_task_id)
    system_args.general_task_id = general_task_id

    scripts = []
    for script_file in build_tasks(job_args, system_args):
        scripts.append(script_file)

    def call_script(script_name):
        print("call_script with:", script_name)
        if CLUSTER_MODE:
            check_call(['qsub', script_name])
        else:
            check_call(['bash', script_name])

    print('task count: ', len(scripts))
    print('worker count: ', WORKER_POOL_SIZE)

    pool = Pool(WORKER_POOL_SIZE)
    pool.map(call_script, scripts)
    pool.close()
    pool.join()

    print("Done! in %s secs" % (dt.datetime.now() - t0).total_seconds())

    return general_task_id
