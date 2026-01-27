import datetime as dt
from argparse import ArgumentParser
from multiprocessing.dummy import Pool
from subprocess import check_call
from typing import Any, Callable, Generator, Literal, cast

import boto3

# Set up your local config, from environment variables, with some sone defaults
from runzi.automation.scaling.local_config import CLUSTER_MODE, WORKER_POOL_SIZE, EnvMode
from runzi.configuration.inversion_diagnostics import build_inversion_diag_tasks
from runzi.configuration.ruptureset_diagnostics import build_rupset_diag_tasks


def run_diagnostic_reports(general_task_id: str, mode=Literal["inversion", "rupture_set"]):
    t0 = dt.datetime.now()
    task_builder: Callable[[str], Generator[dict[str, Any] | str, None, None]]
    if mode == "inversion":
        task_builder = build_inversion_diag_tasks
    elif mode == "rupture_set":
        task_builder = build_rupset_diag_tasks

    def call_script(script_name: str):
        print("call_script with:", script_name)
        if CLUSTER_MODE:
            check_call(['qsub', script_name])
        else:
            check_call(['bash', script_name])

    scripts = []
    for script_file in task_builder(general_task_id):
        print('scheduling: ', script_file)
        scripts.append(script_file)

    if CLUSTER_MODE == EnvMode['LOCAL']:
        print('task count: ', len(scripts))
        pool = Pool(WORKER_POOL_SIZE)
        pool.map(call_script, scripts)
        pool.close()
        pool.join()
    elif CLUSTER_MODE == EnvMode['AWS']:
        batch_client = boto3.client(
            service_name='batch', region_name='us-east-1', endpoint_url='https://batch.us-east-1.amazonaws.com'
        )
        for script_or_config in scripts:
            print('AWS_TIME!: ', script_or_config)
            res = batch_client.submit_job(**script_or_config)
            print(res)
    elif CLUSTER_MODE == EnvMode['CLUSTER']:
        for script_or_config in scripts:
            script_or_config = cast(str, script_or_config)
            call_script(script_or_config)

    print("Done! in %s secs" % (dt.datetime.now() - t0).total_seconds())


if __name__ == "__main__":
    parser = ArgumentParser(description="Create azimuthal rupture sets.")
    parser.add_argument('general_task_id', help="the ID of the GeneralTask that created the inversions")
    parser.add_argument('mode', help="inversion or rupture_set")
    args = parser.parse_args()
    run_diagnostic_reports(args.general_task_id, parser.mode)
