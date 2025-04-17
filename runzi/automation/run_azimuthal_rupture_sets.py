import datetime as dt
import getpass
import itertools
import os
import stat
from multiprocessing.dummy import Pool
from pathlib import PurePath
from subprocess import check_call

import scaling.azimuthal_rupture_set_builder_task
import scaling.coulomb_rupture_set_builder_task
from dateutil.tz import tzutc
from nshm_toshi_client.general_task import GeneralTask

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
)
from scaling.opensha_task_factory import OpenshaTaskFactory

# If you wish to override something in the main config, do so here ..
WORKER_POOL_SIZE = 2

# If using API give this task a descriptive setting...

TASK_TITLE = "Build Azimuthal CFM 0.9 ruptsets with increased minimum sub-sections - take 2"

TASK_DESCRIPTION = """Azimuthal ruptures with new **min_sub_sections filter**

This will increase the minimum rupture magnitudes produced with no effect on larger ruptures.


 - models = [CFM_0_9_SANSTVZ_D90, CFM_0_9_SANSTVZ_2010]
 - strategies = ['UCERF3', ]
 - jump_limits = [5.0,]
 - ddw_ratios = [0.5,]
 - max_cumulative_azimuths = [560.0,]
 - thinning_factors = [0.0, 0.1]
 - min_sub_sects_per_parents = [2,]
 - min_sub_sections = [3,4,5]

"""


def build_tasks(
    general_task_id,
    models,
    jump_limits,
    ddw_ratios,
    strategies,
    max_cumulative_azimuths,
    min_sub_sects_per_parents,
    min_sub_sections_list,
    thinning_factors,
    scaling_relations,
    max_sections=1000,
):
    """
    build the shell scripts 1 per task, based on all the inputs

    """
    task_count = 0
    task_factory = OpenshaTaskFactory(
        OPENSHA_ROOT,
        WORK_PATH,
        scaling.azimuthal_rupture_set_builder_task,
        initial_gateway_port=25333,
        jre_path=OPENSHA_JRE,
        app_jar_path=FATJAR,
        task_config_path=WORK_PATH,
        jvm_heap_max=JVM_HEAP_MAX,
        jvm_heap_start=JVM_HEAP_START,
        pbs_script=CLUSTER_MODE,
    )

    for (
        model,
        strategy,
        distance,
        max_cumulative_azimuth,
        min_sub_sects_per_parent,
        min_sub_sections,
        ddw,
        thinning_factor,
        scaling_relation,
    ) in itertools.product(
        models,
        strategies,
        jump_limits,
        max_cumulative_azimuths,
        min_sub_sects_per_parents,
        min_sub_sections_list,
        ddw_ratios,
        thinning_factors,
        scaling_relations,
    ):

        task_count += 1

        task_arguments = dict(
            max_sections=max_sections,
            down_dip_width=ddw,
            connection_strategy=strategy,
            fault_model=model,  # instead of filename. filekey
            max_jump_distance=distance,
            max_cumulative_azimuth=max_cumulative_azimuth,
            min_sub_sects_per_parent=min_sub_sects_per_parent,
            min_sub_sections=min_sub_sections,
            thinning_factor=thinning_factor,
            scaling_relationship=scaling_relation,
        )

        job_arguments = dict(
            task_id=task_count,
            java_threads=JAVA_THREADS,
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
        return


if __name__ == "__main__":

    t0 = dt.datetime.utcnow()

    GENERAL_TASK_ID = None

    if USE_API:
        headers = {"x-api-key": API_KEY}
        general_api = GeneralTask(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
        # create new task in toshi_api
        GENERAL_TASK_ID = general_api.create_task(
            created=dt.datetime.now(tzutc()).isoformat(),
            agent_name=getpass.getuser(),
            title=TASK_TITLE,
            description=TASK_DESCRIPTION,
        )

    # Test parameters
    models = ["CFM_0_9_SANSTVZ_2010", "CFM_0_9_SANSTVZ_D90"]  # , "CFM_0_9_ALL_D90". "CFM_0_3_SANSTVZ"]
    strategies = [
        'UCERF3',
    ]  # 'POINTS'] #, 'UCERF3' == DOWNDIP]
    jump_limits = [
        5.0,
    ]  # 4.0, 4.5, 5.0, 5.1] #4.0, 4.5, 5.0, 5.1] # , 5.1, 5.2, 5.3]
    ddw_ratios = [
        0.5,
    ]  # 1.0, 1.5, 2.0, 2.5]
    min_sub_sects_per_parents = [
        2,
    ]  # 3,4,5]
    min_sub_sections_list = [3, 4, 5]
    max_cumulative_azimuths = [
        560.0,
    ]  # 570.0, 580, 590.0, 600] # 580.0, 600.0]
    thinning_factors = [0.0, 0.1]  # , 0.2, 0.3] #, 0.05, 0.1, 0.2]
    scaling_relations = [
        'TMG_CRU_2017',
    ]  # 'SHAW_2009_MOD'] WARNING this is not yet configurable, need a setter in ruptset builder

    # limit test size, nomally 1000 for NZ CFM
    MAX_SECTIONS = 200

    pool = Pool(WORKER_POOL_SIZE)

    scripts = []
    for script_file in build_tasks(
        GENERAL_TASK_ID,
        models,
        jump_limits,
        ddw_ratios,
        strategies,
        max_cumulative_azimuths,
        min_sub_sects_per_parents,
        min_sub_sections_list,
        thinning_factors,
        scaling_relations,
        MAX_SECTIONS,
    ):
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

    print("GENERAL_TASK_ID:", GENERAL_TASK_ID)
    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())
