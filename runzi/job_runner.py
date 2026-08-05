"""This module provides the runner JobRunner class for creating running jobs."""

import datetime as dt
import getpass
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from multiprocessing.dummy import Pool
from subprocess import check_call

from runzi.arguments import ArgSweeper, SubmissionArgs, serialize_arguments
from runzi.automation import local_config
from runzi.automation.local_config import WORKER_POOL_SIZE, ClusterModeEnum
from runzi.automation.toshi_api import CreateGeneralTaskArgs, ModelType, SubtaskType
from runzi.aws.session import get_session
from runzi.build_tasks import build_tasks
from runzi.protocols import ModuleWithDefaultSubmissionArgs

from .tasks.toshi_utils import get_toshi_api

logging.basicConfig(level=logging.INFO)

loglevel = logging.INFO
logging.getLogger("py4j.java_gateway").setLevel(loglevel)
logging.getLogger("nshm_toshi_client.toshi_client_base").setLevel(loglevel)
logging.getLogger("nshm_toshi_client.toshi_file").setLevel(loglevel)
logging.getLogger("urllib3").setLevel(loglevel)
logging.getLogger("botocore").setLevel(loglevel)
logging.getLogger("git.cmd").setLevel(loglevel)


class JobRunner(ABC):
    """A class to run jobs."""

    subtask_type: SubtaskType
    job_name: str

    def __init__(self, argument_sweeper: ArgSweeper, task_module: ModuleWithDefaultSubmissionArgs):
        """Initialize the JobRunner.

        Args:
            argument_sweeper: input arguments for the jobs including swept args.
            task_module: the task module to run.
        """
        self.argument_sweeper = argument_sweeper
        self.task_module = task_module
        self.default_submission_args: SubmissionArgs = task_module.default_submission_args

    def set_submission_args(self) -> SubmissionArgs:
        # make a copy here only to make it clear that we have modified it
        submission_args = self.default_submission_args.model_copy(deep=True)
        for name, value in self.argument_sweeper.submission_arg_overrides.items():
            setattr(submission_args, name, value)
        return submission_args

    @abstractmethod
    def get_model_type(self) -> ModelType:
        pass

    def _build_argument_list(self) -> list[dict[str, str | list[str]]]:
        """Build argument list for general task.

        Built from the task objects themselves rather than from the raw config, and serialized
        with serialize_arguments — the same call the subtasks use to record their own arguments.
        That makes every general task value identical to the subtask value it produced. Reading
        swept values straight off the ArgSweeper instead would leak the config file's key order
        into dict arguments (e.g. rupture_set), which no longer matches the field order a subtask
        reports after the value has been through the args model.
        """
        # Collect the distinct values each argument takes across the tasks, in first-seen order.
        # Every task carries a value for every argument, so unswept arguments repeat the same one.
        all_args: defaultdict[str, list[str]] = defaultdict(list)
        for task_args in self.argument_sweeper.get_tasks():
            for name, value in serialize_arguments(task_args).items():
                if value not in all_args[name]:
                    all_args[name].append(value)
        return [dict(k=name, v=values) for name, values in all_args.items()]

    def run_jobs(self) -> str | None:
        """Launch jobs.

        Returns:
            general task ID if using toshi API or None.
        """
        # self.custom_setup()
        t0 = dt.datetime.now()
        self.argument_sweeper.validate_all_tasks()

        # USE_API = False
        general_task_id = None

        args_list = self._build_argument_list()
        model_type = self.get_model_type()

        if local_config.USE_API:
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
            general_task_id = get_toshi_api().general_task.create_task(gt_args)

        print("GENERAL_TASK_ID:", general_task_id)
        submission_args = self.set_submission_args()

        scripts = [
            script_file
            for script_file in build_tasks(
                self.argument_sweeper, submission_args, self.task_module, model_type, self.job_name, general_task_id
            )
        ]
        if local_config.USE_API:
            get_toshi_api().general_task.update_subtask_count(general_task_id, len(scripts))

        if local_config.CLUSTER_MODE is ClusterModeEnum.LOCAL:

            def call_script(script_name):
                print("call_script with:", script_name)
                check_call(["bash", script_name])

            print("task count: ", len(scripts))
            print("worker count: ", WORKER_POOL_SIZE)
            pool = Pool(WORKER_POOL_SIZE)
            pool.map(call_script, scripts)
            pool.close()
            pool.join()
        elif local_config.CLUSTER_MODE is ClusterModeEnum.AWS:
            batch_client = get_session().client(
                service_name='batch', region_name='us-east-1', endpoint_url='https://batch.us-east-1.amazonaws.com'
            )
            for script_or_config in scripts:
                assert isinstance(script_or_config, dict)
                res = batch_client.submit_job(**script_or_config)
                print(res)
        elif local_config.CLUSTER_MODE is ClusterModeEnum.CLUSTER:
            for script_name in scripts:
                assert isinstance(script_name, str)
                check_call(["qsub", script_name])

        print(f'Done! in {(dt.datetime.now() - t0).total_seconds()} secs')

        return general_task_id
