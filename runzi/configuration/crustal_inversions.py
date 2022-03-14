import os
import pwd

import stat
import json
from pathlib import PurePath
from subprocess import check_call
from multiprocessing.dummy import Pool
import boto3

import datetime as dt
import logging

from runzi.automation.scaling.toshi_api import ToshiApi, CreateGeneralTaskArgs
from runzi.automation.scaling.opensha_task_factory import get_factory
from runzi.automation.scaling.file_utils import download_files, get_output_file_id, get_output_file_ids

from runzi.execute import inversion_solution_builder_task
from runzi.util.aws import get_ecs_job_config

# Set up your local config, from environment variables, with some sone defaults
from runzi.automation.scaling.local_config import (OPENSHA_ROOT, WORK_PATH, OPENSHA_JRE, FATJAR,
    JVM_HEAP_MAX, JVM_HEAP_START, USE_API, JAVA_THREADS,
    API_KEY, API_URL, S3_URL, S3_REPORT_BUCKET, CLUSTER_MODE, EnvMode)

from runzi.configuration.crustal_inversion_permutations import *

#JAVA_THREADS = 4

logging.basicConfig()
log = logging.getLogger(__name__)

INITIAL_GATEWAY_PORT = 26533 #set this to ensure that concurrent scheduled tasks won't clash

if CLUSTER_MODE == EnvMode['AWS']:
    WORK_PATH='/WORKING'

def build_crustal_tasks(general_task_id, rupture_sets, args, config):
    task_count = 0

    factory_class = get_factory(CLUSTER_MODE)

    task_factory = factory_class(OPENSHA_ROOT, WORK_PATH, inversion_solution_builder_task,
        initial_gateway_port=INITIAL_GATEWAY_PORT,
        jre_path=OPENSHA_JRE, app_jar_path=FATJAR,
        task_config_path=WORK_PATH, jvm_heap_max=JVM_HEAP_MAX, jvm_heap_start=JVM_HEAP_START)

    config_version = config.get_config_version()
    # Deprecated versions
    # if config_version == "2.0":
    #     permutations_generator = branch_permutations_generator
    # elif config_version == "2.1":
    #     permutations_generator = branch_permutations_generator_21
    # elif config_version == "2.2":
    #     permutations_generator = branch_permutations_generator_22
    # elif config_version == "2.3":
    #     permutations_generator = branch_permutations_generator_23
    # elif config_version == "2.4":
    #     permutations_generator = branch_permutations_generator_24
    # else:
    #     permutations_generator = all_permutations_generator

    if config_version == "2.5":
        permutations_generator = branch_permutations_generator_25
    elif config_version == "3.0":
        permutations_generator = branch_permutations_generator_30
    elif config_version == "3.1":
        permutations_generator = branch_permutations_generator_31
    elif config_version == "3.2":
        permutations_generator = branch_permutations_generator_32
    elif config_version == "3.3":
        permutations_generator = branch_permutations_generator_33
    else:
        raise ValueError(F"Config version {config_version} is not supported")

    log.info(f"Using permutations_generator {permutations_generator} for config version {config_version}.")

    for (rid, rupture_set_info) in rupture_sets.items():

        job_arguments = dict(
            java_threads = config.get_job_args().get("_java_threads", JAVA_THREADS), # JAVA_THREADS,
            jvm_heap_max = JVM_HEAP_MAX,
            working_path=str(WORK_PATH),
            root_folder=OPENSHA_ROOT,
            general_task_id=general_task_id,
            use_api = USE_API,
            )

        for task_arguments in permutations_generator(args, rupture_set_info):

            task_count +=1

            job_arguments['task_id'] = task_count
            job_arguments['java_gateway_port'] = task_factory.get_next_port()


            if CLUSTER_MODE == EnvMode['AWS']:

                job_name = f"Runzi-automation-crustal_inversions-{task_count}"
                config_data = dict(task_arguments=task_arguments, job_arguments=job_arguments)

                yield get_ecs_job_config(job_name, rupture_set_info['id'], config_data,
                    toshi_api_url=API_URL, toshi_s3_url=S3_URL, toshi_report_bucket=S3_REPORT_BUCKET,
                    task_module=inversion_solution_builder_task.__name__,
                    time_minutes=int(task_arguments['max_inversion_time']), memory=30720, vcpu=4)

            else:
                #write a config
                task_factory.write_task_config(task_arguments, job_arguments)

                script = task_factory.get_task_script()

                script_file_path = PurePath(WORK_PATH, f"task_{task_count}.sh")
                with open(script_file_path, 'w') as f:
                    f.write(script)

                #make file executable
                st = os.stat(script_file_path)
                os.chmod(script_file_path, st.st_mode | stat.S_IEXEC)

                yield str(script_file_path)
