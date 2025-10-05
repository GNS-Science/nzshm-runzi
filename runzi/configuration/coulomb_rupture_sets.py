from runzi.automation.scaling.local_config import CLUSTER_MODE, FATJAR, JVM_HEAP_START, OPENSHA_JRE, OPENSHA_ROOT, USE_API, WORK_PATH
from runzi.automation.scaling.opensha_task_factory import get_factory
from runzi.execute import coulomb_rupture_set_builder_task
from runzi.runners.coulomb_rupture_sets import INITIAL_GATEWAY_PORT, JAVA_THREADS, JVM_HEAP_MAX


import itertools
import os
import stat
from pathlib import PurePath


def build_tasks(general_task_id, args):
    """
    build the shell scripts 1 per task, based on all the inputs

    """
    task_count = 0
    factory_class = get_factory(CLUSTER_MODE)

    task_factory = factory_class(
        OPENSHA_ROOT,
        WORK_PATH,
        coulomb_rupture_set_builder_task,
        initial_gateway_port=INITIAL_GATEWAY_PORT,
        jre_path=OPENSHA_JRE,
        app_jar_path=FATJAR,
        task_config_path=WORK_PATH,
        jvm_heap_max=JVM_HEAP_MAX,
        jvm_heap_start=JVM_HEAP_START,
    )

    for (
        model,
        min_sub_sects_per_parent,
        min_sub_sections,
        max_jump_distance,
        adaptive_min_distance,
        thinning_factor,
        max_sections,
        depth_scaling,
        # use_inverted_rake
    ) in itertools.product(
        args['models'],
        args['min_sub_sects_per_parents'],
        args['min_sub_sections_list'],
        args['jump_limits'],
        args['adaptive_min_distances'],
        args['thinning_factors'],
        args['max_sections'],
        args['depth_scaling'],
        # args['use_inverted_rakes']
    ):

        task_count += 1

        task_arguments = dict(
            max_sections=max_sections,
            fault_model=model,  # instead of filename. filekey
            min_sub_sects_per_parent=min_sub_sects_per_parent,
            min_sub_sections=min_sub_sections,
            max_jump_distance=max_jump_distance,
            adaptive_min_distance=adaptive_min_distance,
            thinning_factor=thinning_factor,
            scaling_relationship='SIMPLE_CRUSTAL',  # TMG_CRU_2017, 'SHAW_2009_MOD' default
            depth_scaling_tvz=depth_scaling['tvz'],
            depth_scaling_sans=depth_scaling['sans'],
            # use_inverted_rake=use_inverted_rake
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
            short_name=f'{model}-{thinning_factor}',
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