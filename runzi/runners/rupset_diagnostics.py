import base64
import datetime as dt
import logging
import os
import stat
from argparse import ArgumentParser
from multiprocessing.dummy import Pool
from pathlib import PurePath
from subprocess import check_call

from runzi.automation.scaling import ruptset_diags_report_task
from runzi.automation.scaling.file_utils import download_files, get_output_file_id, get_output_file_ids
from runzi.automation.scaling.local_config import (
    API_KEY,
    API_URL,
    CLUSTER_MODE,
    FATJAR,
    JVM_HEAP_START,
    OPENSHA_JRE,
    OPENSHA_ROOT,
    REPORT_LEVEL,
    S3_URL,
    USE_API,
    WORK_PATH,
)
from runzi.automation.scaling.opensha_task_factory import OpenshaTaskFactory
from runzi.automation.scaling.toshi_api import ToshiApi

logging.basicConfig(level=logging.INFO)

loglevel = logging.INFO
logging.getLogger('py4j.java_gateway').setLevel(loglevel)
logging.getLogger('nshm_toshi_client.toshi_client_base').setLevel(loglevel)
logging.getLogger('nshm_toshi_client.toshi_file').setLevel(loglevel)
logging.getLogger('urllib3').setLevel(loglevel)
logging.getLogger('git.cmd').setLevel(loglevel)

log = logging.getLogger(__name__)

JVM_HEAP_MAX = 16
JAVA_THREADS = 12


def run_tasks(general_task_id, rupture_sets):
    task_count = 0
    task_factory = OpenshaTaskFactory(
        OPENSHA_ROOT,
        WORK_PATH,
        ruptset_diags_report_task,
        jre_path=OPENSHA_JRE,
        app_jar_path=FATJAR,
        task_config_path=WORK_PATH,
        jvm_heap_max=JVM_HEAP_MAX,
        jvm_heap_start=JVM_HEAP_START,
    )

    for rid, rupture_set_info in rupture_sets.items():

        task_count += 1

        # short_name = f"Rupture set file_id: {rid}"

        # rupture_set_info['info'] has detaail of the Inversion task
        task_arguments = dict(
            rupture_set_file_id=str(rupture_set_info['id']),
            rupture_set_file_path=rupture_set_info['filepath'],
        )

        job_arguments = dict(
            task_id=task_count,
            # round = round,
            java_threads=JAVA_THREADS,
            java_gateway_port=task_factory.get_next_port(),
            working_path=str(WORK_PATH),
            root_folder=OPENSHA_ROOT,
            general_task_id=general_task_id,
            use_api=USE_API,
            build_report_level=REPORT_LEVEL,
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


def run_rupset_diagnostics(args):

    file_or_task_id = args.id
    t0 = dt.datetime.now()
    worker_pool_size = args.num_workers

    GENERAL_TASK_ID = None

    headers = {"x-api-key": API_KEY}

    # general_api = GeneralTask(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
    toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

    # get input files from API

    """
    CHOOSE ONE OF:

        - file_generator = get_output_file_id(file_api, file_id)
        - file_generator = get_output_file_ids(general_api, upstream_task_id)
    """
    # for a single rupture set, pass a valid FileID, for
    if 'GeneralTask' in str(base64.b64decode(file_or_task_id)):
        file_generator = get_output_file_ids(toshi_api, file_or_task_id)
    else:
        file_generator = get_output_file_id(toshi_api, file_or_task_id)  # for file by file ID
    rupture_sets = download_files(toshi_api, file_generator, str(WORK_PATH), overwrite=False)

    pool = Pool(worker_pool_size)

    scripts = []
    for script_file in run_tasks(GENERAL_TASK_ID, rupture_sets):
        print('scheduling: ', script_file)
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


def parse_args():
    parser = ArgumentParser(description="Run diagnostics (report generation) for rupture sets.")
    parser.add_argument(
        "id",
        help="""toshi ID of rutpure set (generate single report) or GeneralTask (generate multiple reports, one for
        each rupture set created by GeneralTask).""",
    )
    parser.add_argument("-n", "--num-workers", type=int, default=1, help="number of parallel workers")
    args = parser.parse_args()
    return args


if __name__ == "__main__":
    run_rupset_diagnostics(parse_args())
