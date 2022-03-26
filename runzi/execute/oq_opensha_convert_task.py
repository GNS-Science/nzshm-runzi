#!python3 oq_opensha_convert.py
import argparse
import json
import base64
import uuid

import os
import sys
import toml
from pathlib import Path, PurePath
from importlib import import_module
import datetime as dt
from dateutil.tz import tzutc

from runzi.automation.scaling.toshi_api import ToshiApi, SubtaskType

from runzi.automation.scaling.local_config import (API_KEY, API_URL, S3_URL)
from nshm_toshi_client.task_relation import TaskRelation #TODO deprecate

required_imports = [
    'openquake.baselib.sap',
    'openquake.hazardlib.sourcewriter.write_source_model',
    'openquake.converters.ucerf.parsers.sections_geojson.get_multi_fault_source' ]

class BuilderTask():

    def __init__(self, job_args):

        self.use_api = job_args.get('use_api', False)
        self._output_folder = PurePath(job_args.get('working_path'))

        if self.use_api:
            headers={"x-api-key":API_KEY}
            self._toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
            self._task_relation_api = TaskRelation(API_URL, None, with_schema_validation=True, headers=headers)

    def run(self, task_arguments, job_arguments):
        # Run the task....
        t0 = dt.datetime.utcnow()
        ta, ja = task_arguments, job_arguments

        environment = {}

        if self.use_api:
            #create new task in toshi_api
            task_id = self._toshi_api.automation_task.create_task(
                dict(
                    created=dt.datetime.now(tzutc()).isoformat(),
                    task_type=SubtaskType.SOLUTION_TO_NRML.name,
                    model_type=ta['model_type'].upper(),
                    ),
                arguments=task_arguments,
                environment=environment
                )

            #link task to the parent task
            self._task_relation_api.create_task_relation(job_arguments['general_task_id'], task_id)

            #link task to the input solution
            input_file_id = task_arguments.get('solution_id')
            if input_file_id:
                self._toshi_api.automation_task.link_task_file(task_id, input_file_id, 'READ')
        else:
            task_id = str(uuid.uuid4())


        # Run the task....
        src_folder = Path(self._output_folder, ta['solution_id'])
        src_folder.mkdir(parents=True, exist_ok=True)

        def convert():
            for mod in required_imports:
                import_module(mod)

            computed = get_multi_fault_source(src_folder, dip_sd, strike_sd, source_id,
                                                      source_name, tectonic_region_type,
                                                      investigation_time)

            print(computed)
            Path(out_folder).mkdir(parents=True, exist_ok=True)
            out_file = os.path.join(out_folder, f'{source_id}-ruptures.xml')
            write_source_model(out_file, [computed], name=source_name, investigation_time=investigation_time)
            print('Created output in: {:s}'.format(out_folder))

            ##TODO zip this and return the archive path

        #DOIT
        convert()

        t1 = dt.datetime.utcnow()
        print("Conversion took %s secs" % (t1-t0).total_seconds())

        if self.use_api:
            #record the completed task

            #the geojson
            #self._toshi_api.automation_task.upload_task_file(task_id, result["geofile"], 'WRITE')

            # #the python log files
            # python_log_file = self._output_folder.joinpath(f"python_script.{job_arguments['java_gateway_port']}.log")
            # self._toshi_api.automation_task.upload_task_file(task_id, python_log_file, 'WRITE')

            #upload the task output
            nrml_id = self._toshi_api.inversion_solution_nrml.upload_inversion_solution_nrml(
                task_id,
                source_solution_id=input_file_id,
                filepath="requirements.txt",
                meta=task_arguments, metrics=None)
                # meta=None,  metrics=None)

                #     .upload_inversion_solution(task_id,
                #         filepath=result['solution'],

            print("created nrml: ", nrml_id)

            done_args = {
             'task_id':task_id,
             'duration':(dt.datetime.utcnow() - t0).total_seconds(),
             'result':"SUCCESS",
             'state':"DONE",
            }
            self._toshi_api.automation_task.complete_task(done_args, {})

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

