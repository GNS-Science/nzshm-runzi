"""This module provides the runner JobRunner class for creating running jobs."""

import datetime as dt
import getpass
import logging
from abc import ABC, abstractmethod
from multiprocessing.dummy import Pool
from subprocess import check_call
from types import ModuleType

import boto3

from runzi.arguments import ArgSweeper, SystemArgs
from runzi.automation.scaling.local_config import CLUSTER_MODE, USE_API, WORKER_POOL_SIZE, EnvMode
from runzi.automation.scaling.toshi_api import CreateGeneralTaskArgs, ModelType, SubtaskType
from runzi.build_tasks import build_tasks

from .tasks.toshi_utils import toshi_api

logging.basicConfig(level=logging.INFO)

loglevel = logging.INFO
logging.getLogger('py4j.java_gateway').setLevel(loglevel)
logging.getLogger('nshm_toshi_client.toshi_client_base').setLevel(loglevel)
logging.getLogger('nshm_toshi_client.toshi_file').setLevel(loglevel)
logging.getLogger('urllib3').setLevel(loglevel)
logging.getLogger('botocore').setLevel(loglevel)
logging.getLogger('git.cmd').setLevel(loglevel)


class JobRunner(ABC):
    """A class to run jobs."""

    subtask_type: SubtaskType
    job_name: str

    def __init__(self, argument_sweeper: ArgSweeper, task_module: ModuleType):
        """Initialize the JobRunner.

        Args:
            argument_sweeper: input arguments for the jobs including swept args.
            task_module: the task module to run.
        """
        self.argument_sweeper = argument_sweeper
        self.task_module = task_module
        self.default_sys_args: SystemArgs = task_module.default_system_args

    def set_system_args(self, general_task_id: str | None = None) -> SystemArgs:
        # make a copy here only to make it clear that we have modified it
        system_args = self.default_sys_args.model_copy(deep=True)
        system_args.general_task_id = general_task_id
        for name, value in self.argument_sweeper.sys_arg_overrides.items():
            setattr(self.default_sys_args, name, value)
        return system_args

    @abstractmethod
    def get_model_type(self) -> ModelType:
        pass

    def _build_argument_list(self) -> list[dict[str, str | list[str]]]:
        """Build argument list for general task."""
        unswepped_args = {k: [str(v)] for k, v in self.argument_sweeper.prototype_args.model_dump().items()}
        swept_args = {k: [str(item) for item in v] for k, v in self.argument_sweeper.swept_args.items()}
        all_args = unswepped_args | swept_args
        return [dict(k=key, v=value) for key, value in all_args.items()]

    def run_jobs(self) -> str | None:
        """Launch jobs.

        Returns:
            general task ID if using toshi API or None.
        """
        # self.custom_setup()
        t0 = dt.datetime.now()

        # USE_API = False
        general_task_id = None

        args_list = self._build_argument_list()
        model_type = self.get_model_type()

        if USE_API:

            gt_args = (
                CreateGeneralTaskArgs(
                    agent_name=getpass.getuser(),
                    title=self.argument_sweeper.title,
                    description=self.argument_sweeper.description,
                )
                .set_argument_list(args_list)
                .set_subtask_type(self.subtask_type)
                .set_model_type(model_type)
            )
            general_task_id = toshi_api.general_task.create_task(gt_args)

        print("GENERAL_TASK_ID:", general_task_id)
        system_args = self.set_system_args(general_task_id)

        scripts = [
            script_file
            for script_file in build_tasks(
                self.argument_sweeper, system_args, self.task_module, model_type, self.job_name
            )
        ]
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
                check_call(['qsub', script_name])  # type: ignore

        print("Done! in %s secs" % (dt.datetime.now() - t0).total_seconds())

        return general_task_id
