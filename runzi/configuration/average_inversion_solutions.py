import os
import stat
from pathlib import PurePath

from runzi.configuration.arguments import SystemArgs
import runzi.execute.average_solutions_task
from runzi.automation.scaling.local_config import API_URL, CLUSTER_MODE, S3_REPORT_BUCKET, S3_URL, WORK_PATH, EnvMode
from runzi.automation.scaling.python_task_factory import get_factory
from runzi.runners.runner_inputs import AverageSolutionsInput
from runzi.util.aws import get_ecs_job_config

MAX_JOB_TIME_SECS = 60 * 10


def build_average_tasks(user_args: AverageSolutionsInput, system_args: SystemArgs):

    factory_class = get_factory(CLUSTER_MODE)

    factory_task = runzi.execute.average_solutions_task
    task_factory = factory_class(WORK_PATH, factory_task, task_config_path=WORK_PATH)

    # for source_solution_ids in subtask_arguments['source_solution_groups']:
    for task_count, source_solution_ids in enumerate(user_args.solution_groups, start=1):

        task_system_args = system_args.model_copy(deep=True)
        task_system_args.task_count = task_count

        task_user_args = user_args.model_copy(deep=True)
        task_user_args.solution_groups = [source_solution_ids]

        if CLUSTER_MODE == EnvMode['AWS']:
            job_name = f"Runzi-automation-inversion_diagnostic-{task_count}"

            yield get_ecs_job_config(
                job_name,
                source_solution_ids[0],
                task_user_args,
                task_system_args,
                toshi_api_url=API_URL,
                toshi_s3_url=S3_URL,
                toshi_report_bucket=S3_REPORT_BUCKET,
                task_module=factory_task.__name__,
                time_minutes=int(MAX_JOB_TIME_SECS),
                memory=30720,
                vcpu=4,
            )
        else:
            # write a config
            task_factory.write_task_config(task_user_args, task_system_args)
            script, next_task = task_factory.get_task_script()

            script_file_path = PurePath(WORK_PATH, f"task_{task_count}.sh")
            with open(script_file_path, 'w') as f:
                f.write(script)

            # make file executable
            st = os.stat(script_file_path)
            os.chmod(script_file_path, st.st_mode | stat.S_IEXEC)

            yield str(script_file_path)
