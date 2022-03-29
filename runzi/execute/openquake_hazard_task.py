#!python3 openquake_hazard_task.py
import argparse
import json
import base64
import uuid

import os
import io
import zipfile

from pathlib import Path, PurePath
from importlib import import_module
import datetime as dt
from dateutil.tz import tzutc

from runzi.automation.scaling.toshi_api import ToshiApi, SubtaskType
from runzi.automation.scaling.local_config import (API_KEY, API_URL, S3_URL, WORK_PATH)

import subprocess

class BuilderTask():

    def __init__(self, job_args):

        self.use_api = job_args.get('use_api', False)
        self._output_folder = PurePath(job_args.get('working_path'))

        # if self.use_api:
        #     headers={"x-api-key":API_KEY}
        #     self._toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
        #     self._task_relation_api = TaskRelation(API_URL, None, with_schema_validation=True, headers=headers)

    def run(self, task_arguments, job_arguments):
        # Run the task....
        t0 = dt.datetime.utcnow()
        ta, ja = task_arguments, job_arguments

        '''
            task_arguments = dict(
                tectonic_region_type = tectonic_region_type,
                solution_id = str(solution_info['id']),
                file_name = solution_info['info']['file_name'],
                model_type = model_type,
                config_file = subtask_arguments['config_file'],
                work_folder = subtask_arguments['work_folder'],
                upstream_general_task=source_gt_id
                )

            print(task_arguments)

            job_arguments = dict(
                task_id = task_count,
                working_path = str(WORK_PATH),
                general_task_id = general_task_id,
                use_api = USE_API,
                )
        '''

        configfile = Path(ja['working_path'], ta["work_folder"], ta["config_file"])
        logfile = Path(ja['working_path'], ta["work_folder"], "jobs", f'{ta["solution_id"]}.log')

        try:

            #oq engine --run /WORKING/examples/18_SWRG_INIT/4-sites_many-periods_vs30-475.ini -L /WORKING/examples/18_SWRG_INIT/jobs/BG_unscaled.log
            cmd = ['oq', 'engine',f'--config-file',  f'{configfile}', f'-L',  f'{logfile}']

            print(f'cmd: {cmd}')
            subprocess.check_call(cmd)

            def get_last_task():
                """
                root@tryharder-ubuntu:/app# oq engine --lhc
                job_id |     status |          start_time |         description
                     6 |   complete | 2022-03-29 01:12:16 | 35 sites, few periods
                """

                cmd = ['oq', 'engine', '--lhc']
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
                out, err = p.communicate()

                fileish = io.StringIO()
                fileish.write(out.decode())
                fileish.seek(0)

                fileish.readline() #consume header
                lines = fileish.readlines()
                for line in fileish.readlines():
                    print(line)
                    task = int(line.split("|")[0])

                return task

            last_task = get_last_task()

            output_path = Path(WORK_PATH, ta["work_folder"], "output")

            #get the job ID

            """
            oq engine --export-outputs 12 /WORKING/examples/output/PROD/34-sites-few-CRU+BG
            cp /home/openquake/oqdata/calc_12.hdf5 /WORKING/examples/output/PROD
            """
            cmd = ['oq', 'engine',f'--export-outputs', f'{last_task}', f'-L', f'{output_path}']
            print(f'cmd: {cmd}')
            subprocess.check_call(cmd)

            cmd = ["cp", f"/home/openquake/oqdata/calc_{last_task}.hdf5", str(output_path)]
            print(f'cmd: {cmd}')
            subprocess.check_call(cmd)

        except Exception as err:
            print(f"check_call err: {err}")

        t1 = dt.datetime.utcnow()
        print("Task took %s secs" % (t1-t0).total_seconds())


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    args = parser.parse_args()

    try:
        # LOCAL and CLUSTER this is a file
        config_file = args.config
        f= open(args.config, 'r', encoding='utf-8')
        config = json.load(f)
    except:
        # for AWS this must be a quoted JSON string
        config = json.loads(urllib.parse.unquote(args.config))

    task = BuilderTask(config['job_arguments'])
    task.run(**config)
