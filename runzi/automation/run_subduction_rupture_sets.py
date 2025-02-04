"""
Configuration for building subduction rupture sets.
"""

import datetime as dt
import itertools
import os
import pwd
import stat
from multiprocessing.dummy import Pool
from pathlib import PurePath
from subprocess import check_call

from dateutil.tz import tzutc

# Set up your local config, from environment variables, with some sone defaults
from scaling.local_config import (
    API_KEY,
    API_URL,
    CLUSTER_MODE,
    FATJAR,
    JAVA_THREADS,
    JVM_HEAP_MAX,
    JVM_HEAP_START,
    OPENSHA_JRE,
    OPENSHA_ROOT,
    S3_URL,
    USE_API,
    WORK_PATH,
    EnvMode,
)

from runzi.automation.scaling import subduction_rupture_set_builder_task
from runzi.automation.scaling.opensha_task_factory import get_factory
from runzi.automation.scaling.toshi_api import CreateGeneralTaskArgs, ModelType, SubtaskType, ToshiApi

# If you wish to override something in the main config, do so here ..
WORKER_POOL_SIZE = 1
JVM_HEAP_MAX = 12
JVM_HEAP_START = 2

INITIAL_GATEWAY_PORT = 26533  # set this to ensure that concurrent scheduled tasks won't clash
MAX_JOB_TIME_SECS = 60 * 30  # Change this soon

if CLUSTER_MODE == EnvMode['AWS']:
    WORK_PATH = '/WORKING'


def build_tasks(general_task_id, args):
    """
    build the shell scripts 1 per task, based on all the inputs

    """
    task_count = 0
    factory_class = get_factory(CLUSTER_MODE)

    task_factory = factory_class(
        OPENSHA_ROOT,
        WORK_PATH,
        subduction_rupture_set_builder_task,
        initial_gateway_port=INITIAL_GATEWAY_PORT,
        jre_path=OPENSHA_JRE,
        app_jar_path=FATJAR,
        task_config_path=WORK_PATH,
        jvm_heap_max=JVM_HEAP_MAX,
        jvm_heap_start=JVM_HEAP_START,
    )

    # task_factory = OpenshaTaskFactory(OPENSHA_ROOT, WORK_PATH, scaling.subduction_rupture_set_builder_task,
    #     initial_gateway_port=25733,
    #     jre_path=OPENSHA_JRE, app_jar_path=FATJAR,
    #     task_config_path=WORK_PATH, jvm_heap_max=JVM_HEAP_MAX, jvm_heap_start=JVM_HEAP_START)
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
        args['models'],
        args['min_aspect_ratios'],
        args['max_aspect_ratios'],
        args['aspect_depth_thresholds'],
        args['min_fill_ratios'],
        args['growth_position_epsilons'],
        args['growth_size_epsilons'],
        args['scaling_relationships'],
        args['deformation_models'],
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
            working_path=str(WORK_PATH),
            root_folder=OPENSHA_ROOT,
            general_task_id=general_task_id,
            use_api=USE_API,
        )

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

        # testing
        # return


if __name__ == "__main__":

    t0 = dt.datetime.utcnow()

    GENERAL_TASK_ID = None
    # USE_API = False
    headers = {"x-api-key": API_KEY}
    toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

    # If using API give this task a descriptive setting...
    TASK_TITLE = "Build Puysegur ruptures - fix dip direction"

    TASK_DESCRIPTION = """
    """
    ##Test parameters
    args = dict(
        models=[
            "SBD_0_2_PUY_15",
        ],  # "SBD_0_1_HKR_KRM_10"]
        min_aspect_ratios=[
            "2.0",
        ],
        max_aspect_ratios=[
            "5.0",
        ],
        aspect_depth_thresholds=[
            "5",
        ],
        min_fill_ratios=["0.1"],  # 0.8, 0.7, 0.6, 0.5, 0.4,0.3", "0.2",
        growth_position_epsilons=["0.0"],  # 0.02, 0.01]
        growth_size_epsilons=["0.0"],  # 0.02, 0.01]
        scaling_relationships=["TMG_SUB_2017"],
        deformation_models=[
            "",
        ],
    )
    args_list = []
    for key, value in args.items():
        args_list.append(dict(k=key, v=value))

    if USE_API:

        subtask_type = SubtaskType.RUPTURE_SET
        model_type = ModelType.SUBDUCTION
        # create new task in toshi_api
        gt_args = (
            CreateGeneralTaskArgs(
                agent_name=pwd.getpwuid(os.getuid()).pw_name, title=TASK_TITLE, description=TASK_DESCRIPTION
            )
            .set_argument_list(args_list)
            .set_subtask_type(subtask_type)
            .set_model_type(model_type)
        )

        GENERAL_TASK_ID = toshi_api.general_task.create_task(gt_args)

    print("GENERAL_TASK_ID:", GENERAL_TASK_ID)

    pool = Pool(WORKER_POOL_SIZE)

    scripts = []
    for script_file in build_tasks(GENERAL_TASK_ID, args):
        scripts.append(script_file)

    def call_script(script_name):
        print("call_script with:", script_name)
        if CLUSTER_MODE:
            check_call(['qsub', script_name])
        else:
            check_call(['bash', script_name])

    print('task count: ', len(scripts))
    print('worker count: ', WORKER_POOL_SIZE)

    pool.map(call_script, scripts)
    pool.close()
    pool.join()

    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())
