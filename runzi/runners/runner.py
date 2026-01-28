"""This module provides the runner JobRunner class for creating running jobs."""

import datetime as dt
import getpass
import logging
from multiprocessing.dummy import Pool
from subprocess import check_call
from types import ModuleType

import boto3

from runzi.automation.scaling.local_config import (
    API_KEY,
    API_URL,
    CLUSTER_MODE,
    S3_URL,
    USE_API,
    WORKER_POOL_SIZE,
    EnvMode,
)
from runzi.automation.scaling.toshi_api import CreateGeneralTaskArgs, ToshiApi
from runzi.configuration.configuration import build_tasks
from runzi.execute.arguments import ArgSweeper, SystemArgs
from .utils import toshi_api

logging.basicConfig(level=logging.INFO)

loglevel = logging.INFO
logging.getLogger('py4j.java_gateway').setLevel(loglevel)
logging.getLogger('nshm_toshi_client.toshi_client_base').setLevel(loglevel)
logging.getLogger('nshm_toshi_client.toshi_file').setLevel(loglevel)
logging.getLogger('urllib3').setLevel(loglevel)
logging.getLogger('botocore').setLevel(loglevel)
logging.getLogger('git.cmd').setLevel(loglevel)


class JobRunner:
    """A class to run jobs."""

    def __init__(self, job_args: ArgSweeper, task_module: ModuleType):
        """Initialize the JobRunner.

        Args:
            job_args: input arguments for the jobs including swept args.
            task_module: the task module to run.
        """
        self.job_args = job_args
        self.task_module = task_module
        self.system_args = SystemArgs(use_api=USE_API)

    def custom_setup(self):
        pass  # Placeholder for any custom setup needed

    def _build_argument_list(self) -> list[dict[str, list[str]]]:
        """Build argument list for general task."""
        unswepped_args = {
            k: [
                str(v),
            ]
            for k, v in self.job_args.prototype.get_run_args().items()
        }
        swepted_args = {k: [str(item) for item in v] for k, v in self.job_args.swept_args.items()}
        all_args = unswepped_args | swepted_args
        return [dict(k=key, v=value) for key, value in all_args.items()]

    def run_jobs(self) -> str | None:
        """Launch jobs.

        Returns:
            general task ID if using toshi API or None.
        """
        self.custom_setup()
        t0 = dt.datetime.now()

        # USE_API = False
        general_task_id = None

        args_list = self._build_argument_list()

        if USE_API:

            gt_args = (
                CreateGeneralTaskArgs(
                    agent_name=getpass.getuser(), title=self.job_args.title, description=self.job_args.description
                )
                .set_argument_list(args_list)
                .set_subtask_type(self.system_args.subtask_type)
                .set_model_type(self.system_args.model_type)
            )
            general_task_id = toshi_api.general_task.create_task(gt_args)

        print("GENERAL_TASK_ID:", general_task_id)
        self.system_args.general_task_id = general_task_id

        scripts = [script_file for script_file in build_tasks(self.job_args, self.system_args, self.task_module)]
        if USE_API:
            toshi_api.general_task.update_subtask_count(general_task_id, len(scripts))

        if CLUSTER_MODE is EnvMode.LOCAL:

            def call_script(script_name):
                print("call_script with:", script_name)
                check_call(['bash', script_name])

            print('task count: ', len(scripts))
            print('worker count: ', WORKER_POOL_SIZE)
            pool = Pool(WORKER_POOL_SIZE)
            pool.map(call_script, scripts)
            pool.close()
            pool.join()
        elif CLUSTER_MODE is EnvMode.AWS:
            batch_client = boto3.client(
                service_name='batch', region_name='us-east-1', endpoint_url='https://batch.us-east-1.amazonaws.com'
            )
            for script_or_config in scripts:
                res = batch_client.submit_job(**script_or_config)
                print(res)
        elif CLUSTER_MODE is EnvMode.CLUSTER:
            for script_name in scripts:
                check_call(['qsub', script_name])

        print("Done! in %s secs" % (dt.datetime.now() - t0).total_seconds())

        return general_task_id


