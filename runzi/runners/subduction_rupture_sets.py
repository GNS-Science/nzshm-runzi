"""This module provides the runner function to build subduction rupture sets."""

import datetime as dt
import getpass
import itertools
import os
import stat
from argparse import ArgumentParser
from multiprocessing.dummy import Pool
from pathlib import Path, PurePath
from subprocess import check_call

from runzi.automation.scaling import subduction_rupture_set_builder_task

# Set up your local config, from environment variables, with some sone defaults
from runzi.automation.scaling.local_config import (
    API_KEY,
    API_URL,
    CLUSTER_MODE,
    FATJAR,
    JAVA_THREADS,
    OPENSHA_JRE,
    OPENSHA_ROOT,
    S3_URL,
    USE_API,
    WORK_PATH,
    EnvMode,
)
from runzi.automation.scaling.opensha_task_factory import get_factory
from runzi.automation.scaling.toshi_api import CreateGeneralTaskArgs, ModelType, SubtaskType, ToshiApi
from runzi.runners.runner_inputs import InputBase

JVM_HEAP_MAX = 12
JVM_HEAP_START = 2

INITIAL_GATEWAY_PORT = 26533  # set this to ensure that concurrent scheduled tasks won't clash
MAX_JOB_TIME_SECS = 60 * 30  # Change this soon


class SubductionRuptureSetsInput(InputBase):
    models: list[str]
    min_aspect_ratios: list[float]
    max_aspect_ratios: list[float]
    aspect_depth_thresholds: list[int]
    min_fill_ratios: list[float]
    growth_position_epsilons: list[float]
    growth_size_epsilons: list[float]
    scaling_relationships: list[str]
    deformation_models: list[str]


def build_tasks(general_task_id, job_input: SubductionRuptureSetsInput):
    """
    build the shell scripts 1 per task, based on all the inputs

    """
    work_path = '/WORKING' if CLUSTER_MODE == EnvMode['AWS'] else WORK_PATH
    task_count = 0
    factory_class = get_factory(CLUSTER_MODE)

    task_factory = factory_class(
        OPENSHA_ROOT,
        work_path,
        subduction_rupture_set_builder_task,
        initial_gateway_port=INITIAL_GATEWAY_PORT,
        jre_path=OPENSHA_JRE,
        app_jar_path=FATJAR,
        task_config_path=work_path,
        jvm_heap_max=JVM_HEAP_MAX,
        jvm_heap_start=JVM_HEAP_START,
    )

    # task_factory = OpenshaTaskFactory(OPENSHA_ROOT, work_path, scaling.subduction_rupture_set_builder_task,
    #     initial_gateway_port=25733,
    #     jre_path=OPENSHA_JRE, app_jar_path=FATJAR,
    #     task_config_path=work_path, jvm_heap_max=JVM_HEAP_MAX, jvm_heap_start=JVM_HEAP_START)
    for (
        model,
        min_aspect_ratio,
        max_aspect_ratio,
        aspect_depth_threshold,
        min_fill_ratio,
        growth_position_epsilon,
        growth_size_epsilon,
        scaling_relationship,
        deformation_model,
    ) in itertools.product(
        job_input.models,
        job_input.min_aspect_ratios,
        job_input.max_aspect_ratios,
        job_input.aspect_depth_thresholds,
        job_input.min_fill_ratios,
        job_input.growth_position_epsilons,
        job_input.growth_size_epsilons,
        job_input.scaling_relationships,
        job_input.deformation_models,
    ):

        task_count += 1

        task_arguments = dict(
            fault_model=model,
            min_aspect_ratio=min_aspect_ratio,
            max_aspect_ratio=max_aspect_ratio,
            aspect_depth_threshold=aspect_depth_threshold,
            min_fill_ratio=min_fill_ratio,
            growth_position_epsilon=growth_position_epsilon,
            growth_size_epsilon=growth_size_epsilon,
            scaling_relationship=scaling_relationship,
            slip_along_rupture_model='UNIFORM',
            deformation_model=deformation_model,
        )

        job_arguments = dict(
            task_id=task_count,
            java_threads=JAVA_THREADS,
            PROC_COUNT=JAVA_THREADS,
            JVM_HEAP_MAX=JVM_HEAP_MAX,
            java_gateway_port=task_factory.get_next_port(),
            working_path=str(work_path),
            root_folder=OPENSHA_ROOT,
            general_task_id=general_task_id,
            use_api=USE_API,
        )

        # write a config
        task_factory.write_task_config(task_arguments, job_arguments)
        script = task_factory.get_task_script()

        script_file_path = PurePath(work_path, f"task_{task_count}.sh")
        with open(script_file_path, 'w') as f:
            f.write(script)
        # make file executable
        st = os.stat(script_file_path)
        os.chmod(script_file_path, st.st_mode | stat.S_IEXEC)

        yield str(script_file_path)


def run_subduction_rupture_sets(job_input: SubductionRuptureSetsInput) -> str | None:

    t0 = dt.datetime.now()

    general_task_id = None
    headers = {"x-api-key": API_KEY}
    toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

    task_title = job_input.title
    task_description = job_input.description
    worker_pool_size = job_input.worker_pool_size

    args_list = []
    for key, value in job_input.model_dump().items():
        args_list.append(dict(k=key, v=value))

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
        job_input = SubductionRuptureSetsInput.from_toml(input_file)
    run_subduction_rupture_sets(job_input)
