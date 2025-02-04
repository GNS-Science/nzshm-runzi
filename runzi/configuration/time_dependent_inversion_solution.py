import datetime as dt
import itertools
import os
import pwd
import stat
from pathlib import PurePath

import boto3
from dateutil.tz import tzutc

import runzi.execute.time_dependent_solution_task
from runzi.automation.scaling.file_utils import download_files, get_output_file_id, get_output_file_ids
from runzi.automation.scaling.local_config import (
    API_KEY,
    API_URL,
    CLUSTER_MODE,
    FATJAR,
    JAVA_THREADS,
    JVM_HEAP_MAX,
    JVM_HEAP_START,
    OPENSHA_JRE,
    OPENSHA_ROOT,
    USE_API,
    WORK_PATH,
    EnvMode,
)
from runzi.automation.scaling.opensha_task_factory import get_factory
from runzi.automation.scaling.toshi_api import ModelType, SubtaskType, ToshiApi
from runzi.util.aws import get_ecs_job_config

INITIAL_GATEWAY_PORT = 26533  # set this to ensure that concurrent scheduled tasks won't clash


def build_time_dependent_tasks(
    general_task_id: str, subtask_type: SubtaskType, model_type: ModelType, subtask_arguments, toshi_api: ToshiApi
):

    task_count = 0
    factory_class = get_factory(CLUSTER_MODE)

    factory_task = runzi.execute.time_dependent_solution_task
    # task_factory = factory_class(WORK_PATH, factory_task, task_config_path=WORK_PATH)

    task_factory = factory_class(
        OPENSHA_ROOT,
        WORK_PATH,
        factory_task,
        initial_gateway_port=INITIAL_GATEWAY_PORT,
        jre_path=OPENSHA_JRE,
        app_jar_path=FATJAR,
        task_config_path=WORK_PATH,
        jvm_heap_max=JVM_HEAP_MAX,
        jvm_heap_start=JVM_HEAP_START,
    )

    file_generators = []
    for input_id in subtask_arguments['source_solution_ids']:
        file_generators.append(get_output_file_id(toshi_api, input_id))  # for file by file ID

    source_solutions = download_files(
        toshi_api,
        itertools.chain(*file_generators),
        str(WORK_PATH),
        overwrite=False,
        skip_download=(CLUSTER_MODE == EnvMode['AWS']),
    )

    for src_sol_id, src_sol_info in source_solutions.items():

        for (
            current_year,
            mre_enum,
            forecast_timespan,
            aperiodicity,
        ) in itertools.product(
            subtask_arguments["current_years"],
            subtask_arguments['mre_enums'],
            subtask_arguments['forecast_timespans'],
            subtask_arguments['aperiodicities'],
        ):

            task_count += 1

            task_arguments = dict(
                current_year=current_year,
                mre_enum=mre_enum,
                forecast_timespan=forecast_timespan,
                aperiodicity=aperiodicity,
                model_type=model_type.name,
                file_path=src_sol_info['filepath'],
            )

            print(task_arguments)

            job_arguments = dict(
                task_id=task_count,
                source_solution_id=src_sol_id,
                source_solution_info=src_sol_info,
                working_path=str(WORK_PATH),
                general_task_id=general_task_id,
                use_api=USE_API,
                java_threads=JAVA_THREADS,
                java_gateway_port=task_factory.get_next_port(),
                root_folder=OPENSHA_ROOT,
            )

            if CLUSTER_MODE == EnvMode['AWS']:
                pass
                # job_name = f"Runzi-automation-subduction_inversions-{task_count}"
                # config_data = dict(task_arguments=task_arguments, job_arguments=job_arguments)

                # yield get_ecs_job_config(job_name, solution_info['id'], config_data,
                #     toshi_api_url=API_URL, toshi_s3_url=S3_URL, toshi_report_bucket=S3_REPORT_BUCKET,
                #     task_module=inversion_solution_builder_task.__name__,
                #     time_minutes=int(max_inversion_time), memory=30720, vcpu=4)

            else:
                # write a config
                task_factory.write_task_config(task_arguments, job_arguments)
                script = task_factory.get_task_script()

                script_file_path = PurePath(WORK_PATH, f"task_{task_count}.sh")
                with open(script_file_path, 'w') as f:
                    f.write(script)

                # make file executable
                st = os.stat(script_file_path)
                os.chmod(script_file_path, st.st_mode | stat.S_IEXEC)

                yield str(script_file_path)
