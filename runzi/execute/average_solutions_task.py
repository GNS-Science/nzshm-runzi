import json
import urllib
import argparse
import time
import uuid
import datetime as dt
from pathlib import PurePath
from dateutil.tz import tzutc

from solvis import *

from nshm_toshi_client.task_relation import TaskRelation
from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.automation.scaling.toshi_api.general_task import SubtaskType
from runzi.automation.scaling.local_config import (WORK_PATH, API_KEY, API_URL, S3_URL)


class BuilderTask():
    """
    The python client for solution rate averaging
    """

    def __init__(self, job_args):

        self.use_api = job_args.get('use_api', False)
        self._output_folder = PurePath(job_args.get('working_path'))

        if self.use_api:
            headers={"x-api-key":API_KEY}
            self._toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
            self._task_relation_api = TaskRelation(API_URL, None, with_schema_validation=True, headers=headers)


    def run(self, task_arguments, job_arguments):
        
        t0 = dt.datetime.utcnow()
        
        environment = {}

        if self.use_api:
            #create new task in toshi_api
            print(task_arguments)
            task_id = self._toshi_api.automation_task.create_task(
                dict(
                    created=dt.datetime.now(tzutc()).isoformat(),
                    task_type=SubtaskType.SCALE_SOLUTION.name,
                    model_type=task_arguments['model_type'],
                    ),
                arguments=task_arguments,
                environment=environment
                )

            #link automation task to the parent general task
            self._task_relation_api.create_task_relation(job_arguments['general_task_id'], task_id)

            #link task to the input solution
            input_file_id = job_arguments.get('source_solution_id')
            if input_file_id:
                self._toshi_api.automation_task.link_task_file(task_id, input_file_id, 'READ')

        else:
            task_id = str(uuid.uuid4())

        ##DO THE WORK
        soln_filepaths = [li['filepath'] for li in job_arguments['source_solution_info']]
        result = self.averageRuptureRates(soln_filepaths, task_id)

        # SAVE the results
        if self.use_api:
            
            # record the complteded task
            done_args = {
             'task_id':task_id,
             'duration':(dt.datetime.utcnow() - t0).total_seconds(),
             'result':"SUCCESS",
             'state':"DONE",
            }
            self._toshi_api.automation_task.complete_task(done_args, result['metrics'])

            #add the log files
            pyth_log_file = self._output_folder.joinpath(f"python_script.{job_arguments['task_id']}.log")
            self._toshi_api.automation_task.upload_task_file(task_id, pyth_log_file, 'WRITE')

            # get the predecessors
            source_solution_ids = job_arguments.get('source_solution_ids')
            predecessors = []
            for source_solution_id in source_solution_ids:
                predecessors.append(dict(id=source_solution_id,depth=-1))
                source_predecessors = self._toshi_api.get_predecessors(source_solution_id) 

                if source_predecessors:
                    for predecessor in source_predecessors:
                        predecessor['depth'] += -1
                    predecessors.append(predecessor)

            meta = task_arguments.copy()
            meta['source_solution_ids'] = source_solution_ids
            inversion_id = self._toshi_api.aggregate_inversion_solution.upload_inversion_solution(task_id,
                filepath=result['averaged_solution'],
                source_solution_ids=source_solution_ids,
                aggregation_fn='MEAN',
                predecessors=predecessors,
                meta=meta, metrics=result['metrics'])
            print("created scaled inversion solution: ", inversion_id)

        t1 = dt.datetime.utcnow()
        print("Report took %s secs" % (t1-t0).total_seconds())



    def averageRuptureRates(self, in_solution_filepaths, task_id):

        for i, in_solution_filepath in enumerate(in_solution_filepaths):
            soln = InversionSolution().from_archive(in_solution_filepath)
            if i==0:
                rr = soln.ruptures
                ra = soln.rates
                ri = soln.indices
                ruptures = rr.copy()
                rates = ra.copy()
                indices = ri.copy()
                fault_sections = soln.fault_sections.copy()
            else:
                rates += soln.rates
        rates = rates/len(in_solution_filepaths)

        scaled_soln =  InversionSolution()
        scaled_soln.set_props(rates, ruptures, indices, fault_sections)

        new_archive = PurePath(WORK_PATH, 'NZSHM22_AveragedInversionSolution-' + str(task_id) + '.zip')
                
        scaled_soln.to_archive(new_archive,in_solution_filepath)

        metrics = dict(num_input_solns=len(in_solution_filepaths))
        return dict(averaged_solution = new_archive, metrics=metrics)


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

