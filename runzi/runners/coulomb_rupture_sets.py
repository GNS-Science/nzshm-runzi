"""This module provides the runner function for creating Coulomb rupture sets."""

import datetime as dt
import getpass
import itertools
import logging
import os
import stat
from argparse import ArgumentParser
from multiprocessing.dummy import Pool
from pathlib import Path, PurePath
from subprocess import check_call

from pydantic import BaseModel

from runzi.automation.scaling import coulomb_rupture_set_builder_task
from runzi.automation.scaling.local_config import (
    API_KEY,
    API_URL,
    CLUSTER_MODE,
    FATJAR,
    JVM_HEAP_START,
    OPENSHA_JRE,
    OPENSHA_ROOT,
    S3_URL,
    USE_API,
    WORK_PATH,
)
from runzi.automation.scaling.opensha_task_factory import get_factory
from runzi.automation.scaling.toshi_api import CreateGeneralTaskArgs, ToshiApi
from runzi.runners.runner_inputs import InputBase

logging.basicConfig(level=logging.INFO)

JVM_HEAP_MAX = 32
JAVA_THREADS = 16
INITIAL_GATEWAY_PORT = 26533  # set this to ensure that concurrent scheduled tasks won't clash


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


class CoulombRuptureSetsInput(InputBase):
    """Input for generating Coulomb rupture sets."""

    class DepthScaling(BaseModel):
        tvz: float
        sans: float

    max_sections: int
    models: list[str]
    jump_limits: list[int]
    adaptive_min_distances: list[int]
    thinning_factors: list[float]
    min_sub_sects_per_parents: list[int]
    min_sub_sections_list: list[int]
    depth_scaling: list[DepthScaling]

    # testing
    # return


def run_coulomb_rupture_sets(job_input: CoulombRuptureSetsInput) -> str | None:
    t0 = dt.datetime.now()

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
    worker_pool_size = job_input.worker_pool_size

    depth_scaling = [ds.model_dump() for ds in job_input.depth_scaling]
    args = dict(
        models=job_input.models,
        depth_scaling=depth_scaling,
        jump_limits=job_input.jump_limits,
        adaptive_min_distances=job_input.adaptive_min_distances,
        thinning_factors=job_input.thinning_factors,
        min_sub_sects_per_parents=job_input.min_sub_sections_list,
        min_sub_sections_list=job_input.min_sub_sections_list,
        max_sections=[job_input.max_sections],
    )

    args_list = []
    for key, value in args.items():
        args_list.append(dict(k=key, v=str(value)))

    if USE_API:
        # create new task in toshi_api
        headers = {"x-api-key": API_KEY}
        toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

        gt_args = (
            CreateGeneralTaskArgs(
                agent_name=getpass.getuser(), title=job_input.title, description=job_input.description
            )
            .set_argument_list(args_list)
            .set_subtask_type('RUPTURE_SET')
            .set_model_type('CRUSTAL')
        )
        general_task_id = toshi_api.general_task.create_task(gt_args)

        print("GENERAL_TASK_ID:", general_task_id)

    pool = Pool(worker_pool_size)

    scripts = []
    for script_file in build_tasks(general_task_id, args):
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
    parser = ArgumentParser(description="Create azimuthal rupture sets.")
    parser.add_argument('filename', help="the input filename")
    args = parser.parse_args()
    with Path(args.filename).open() as input_file:
        job_input = CoulombRuptureSetsInput.from_toml(input_file)
    run_coulomb_rupture_sets(job_input)
