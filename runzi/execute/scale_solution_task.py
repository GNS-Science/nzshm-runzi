import argparse
import json

import os
import base64
from pathlib import PurePath, Path
import platform
import urllib
import uuid
import time
import datetime as dt
from dateutil.tz import tzutc

from solvis import *

from nshm_toshi_client.task_relation import TaskRelation
from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.automation.scaling.local_config import (WORK_PATH, API_KEY, API_URL, S3_URL)

class BuilderTask():
    """
    The python client for solution rate scaling
    """
    def __init__(self, job_args):

        self.use_api = job_args.get('use_api', False)
        self._output_folder = PurePath(WORK_PATH)

        if self.use_api:
            headers={"x-api-key":API_KEY}
            # self._ruptgen_api = RuptureGenerationTask(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
            self._toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
            self._task_relation_api = TaskRelation(API_URL, None, with_schema_validation=True, headers=headers)


    def run(self, task_arguments, job_arguments):
        # Run the task....
        t0 = dt.datetime.utcnow()
        
        environment = {}

        if self.use_api:
            #create new task in toshi_api
            task_id = self._toshi_api.automation_task.create_task(
                dict(
                    created=dt.datetime.now(tzutc()).isoformat(),
                    task_type="SCALE_SOLUTION", #TODO should I get this from the general task?
                    model_type=task_arguments['config_type'].upper(),
                    ),
                arguments=task_arguments,
                environment=environment
                )

            #link automation task to the parent general task
            self._task_relation_api.create_task_relation(job_arguments['general_task_id'], task_id)

            # TODO: do we need this?
            #link task to the input solution
            input_file_id = task_arguments.get('source_solution_id')
            if input_file_id:
                self._toshi_api.automation_task.link_task_file(task_id, input_file_id, 'READ')

        else:
            task_id = str(uuid.uuid4())

        ##DO THE WORK
        result = self.scaleRuptureRates(
            job_arguments.get('source_solution_info').get('filepath'),
            task_id,
            task_arguments.get('scale')
        )


        # SAVE the results
        if self.use_api:
            
            done_args = {
             'task_id':task_id,
             'duration':(dt.datetime.utcnow() - t0).total_seconds(),
             'result':"SUCCESS",
             'state':"DONE",
            }
            self._toshi_api.automation_task.complete_task(done_args, result['metrics'])

            #upload the task output
            meta = task_arguments.copy()
            meta['source_solution_id'] = job_arguments.get('source_solution_id')
            inversion_id = self._toshi_api.scaled_inversion_solution.upload_inversion_solution(task_id,
                filepath=result['scaled_solution'],
                source_solution_id=job_arguments.get('source_solution_id'),
                meta=meta, metrics=result['metrics'])
            print("created scaled inversion solution: ", inversion_id)


        t1 = dt.datetime.utcnow()
        print("Report took %s secs" % (t1-t0).total_seconds())


    def scaleRuptureRates(self, in_solution_filepath,task_id,scale):

        soln = InversionSolution().from_archive(in_solution_filepath)

        rr = soln.ruptures
        ra = soln.rates
        ri = soln.indices
        ruptures = rr.copy()
        rates = ra.copy()*scale
        indices = ri.copy()

        #all other props are derived from these ones
        scaled_soln =  InversionSolution()
        scaled_soln.set_props(rates, ruptures, indices, soln.fault_sections.copy())

        new_archive = PurePath(WORK_PATH, 'NZSHM22_ScaledInversionSolution-' + str(task_id) + '.zip')
                
        scaled_soln.to_archive(new_archive,in_solution_filepath)

        metrics = dict(scale=scale)
        return dict(scaled_solution = new_archive, metrics=metrics)
        
        


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

    # Wait for some more time, scaled by taskid to avoid S3 consistency issue
    time.sleep(config['job_arguments']['task_id'] )

    # print(config)
    task = BuilderTask(config['job_arguments'])
    task.run(**config)

