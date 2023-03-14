#!python3 oq_opensha_convert.py
import argparse
import json
import base64
import uuid
import urllib

import os

import zipfile

from pathlib import Path, PurePath
from importlib import import_module
import datetime as dt
from dateutil.tz import tzutc

from runzi.automation.scaling.toshi_api import ToshiApi, SubtaskType

from runzi.automation.scaling.file_utils import get_file_meta

from runzi.automation.scaling.local_config import (API_KEY, API_URL, S3_URL)
from nshm_toshi_client.task_relation import TaskRelation #TODO deprecate

from openquake.baselib import sap
from openquake.hazardlib.sourcewriter import write_source_model
from openquake.converters.ucerf.parsers.sections_geojson import (
    get_multi_fault_source)

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
                    model_type=ta['model_type'], 
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
        src_folder = Path(self._output_folder, "downloads", ta['solution_id'])
        #src_folder.mkdir(parents=True, exist_ok=True)

        # for filename in list(Path(src_folder).glob('*.zip')):
        #get name of zifile like `NZSHM22_InversionSolution-QXV0b21hdGlvblRhc2s6MjQ4OVMycWNI.zip`
        with zipfile.ZipFile(Path(src_folder, ta["file_name"]), 'r') as zip_ref:
            zip_ref.extractall(src_folder)

        def convert(config):

            dip_sd = config['rupture_sampling_distance_km']
            strike_sd = dip_sd
            source_id = config['solution_id'].replace('=', '_')
            source_name = config['solution_id']
            tectonic_region_type = config['tectonic_region_type']
            investigation_time = config['investigation_time_years']
            prefix = config['prefix'].replace('=', '_')

            computed = get_multi_fault_source(src_folder, dip_sd, strike_sd, source_id,
                                                      source_name, tectonic_region_type,
                                                      investigation_time,
                                                      prefix)

            print(computed)

            out_file = os.path.join(self._output_folder, f'{source_id}-ruptures.xml')
            write_source_model(out_file, [computed], name=source_name, investigation_time=investigation_time)

            print(f'Created output in: {self._output_folder}')

            # zip this and return the archive path
            output_zip = Path(self._output_folder, ta["file_name"].replace('.zip', '_nrml.zip')) 
            print(f'output: {output_zip}')
            zfile = zipfile.ZipFile(output_zip, 'w')
            for filename in list(Path(self._output_folder).glob(f'{source_id}*')):
                arcname = str(filename).replace(str(self._output_folder), '')
                zfile.write(filename, arcname )
                print(f'archived {filename} as {arcname}')

            return output_zip

        #DOIT
        output_zip = convert(task_arguments)

        t1 = dt.datetime.utcnow()
        print("Conversion took %s secs" % (t1-t0).total_seconds())

        if self.use_api:    

            #upload the task output
                        
            # get the predecessors
            source_solution_id = task_arguments['solution_id']
            predecessors = [dict(id=source_solution_id,depth=-1),]
            source_predecessors = self._toshi_api.get_predecessors(source_solution_id) 

            if source_predecessors:
                for predecessor in source_predecessors:
                    predecessor['depth'] += -1
                    predecessors.append(predecessor)

            nrml_id = self._toshi_api.inversion_solution_nrml.upload_inversion_solution_nrml(
                task_id,
                source_solution_id=input_file_id,
                filepath=output_zip,
                predecessors=predecessors,
                meta=task_arguments, metrics=None)

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

