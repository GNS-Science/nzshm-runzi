import argparse
import json

import os
import base64
import logging
from pathlib import PurePath, Path
import platform
import urllib
import uuid
import time
import datetime as dt
from dateutil.tz import tzutc
from runzi.automation.scaling.toshi_api.general_task import SubtaskType

from py4j.java_gateway import JavaGateway, GatewayParameters

from runzi.automation.scaling.file_utils import get_file_meta

from nshm_toshi_client.task_relation import TaskRelation
from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.automation.scaling.local_config import (WORK_PATH, API_KEY, API_URL, S3_URL)

logging.basicConfig(level=logging.INFO)

loglevel = logging.INFO
logging.getLogger('py4j.java_gateway').setLevel(loglevel)
logging.getLogger('nshm_toshi_client.toshi_client_base').setLevel(loglevel)
logging.getLogger('nshm_toshi_client.toshi_file').setLevel(loglevel)
logging.getLogger('urllib3').setLevel(loglevel)
logging.getLogger('botocore').setLevel(loglevel)
logging.getLogger('git.cmd').setLevel(loglevel)
logging.getLogger('gql.transport').setLevel(logging.WARN)

log = logging.getLogger(__name__)


class BuilderTask():
    """
    The python client for time dependent rate scaling.
    """
    def __init__(self, job_args):

        self.use_api = job_args.get('use_api', False)
        self._output_folder = PurePath(job_args.get('working_path'))


        #setup the java gateway binding
        self._gateway = JavaGateway(gateway_parameters=GatewayParameters(port=job_args['java_gateway_port']))
        self._time_dependent_generator = self._gateway.entry_point.getTimeDependentRatesGenerator()
        self._output_folder = PurePath(WORK_PATH)

        if self.use_api:
            headers={"x-api-key":API_KEY}
            self._toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
            self._task_relation_api = TaskRelation(API_URL, None, with_schema_validation=True, headers=headers)


    def run(self, task_arguments, job_arguments):
        # Run the task....
        t0 = dt.datetime.utcnow()
        
        environment = {}

        if self.use_api:
            #create new task in toshi_api
            print(task_arguments)
            task_id = self._toshi_api.automation_task.create_task(
                dict(
                    created=dt.datetime.now(tzutc()).isoformat(),
                    task_type=SubtaskType.TIME_DEPENDENT_SOLUTION.name,
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
        ta, ja = task_arguments, job_arguments

        t0 = dt.datetime.utcnow()
        output_file = str(PurePath(job_arguments['working_path'], f"NZSHM22_TimeDependentInversionSolution-{task_id}.zip"))
        self._time_dependent_generator.setSolutionFileName(ta['file_path'])\
            .setCurrentYear(ta['current_year'])\
            .setMREData(ta['mre_enum'])\
            .setForecastTimespan(ta['forecast_timespan'])\
            .setOutputFileName(output_file)

        self._time_dependent_generator.generate()
        log.info(f'Produced file : {output_file}')

        t1 = dt.datetime.utcnow()
        log.info("TimeDependent rates generation took %s secs" % (t1-t0).total_seconds())

        # SAVE the results
        if self.use_api:
            
            # record the complteded task
            done_args = {
             'task_id':task_id,
             'duration':(dt.datetime.utcnow() - t0).total_seconds(),
             'result':"SUCCESS",
             'state':"DONE",
            }
            self._toshi_api.automation_task.complete_task(done_args)

            #add the log files
            pyth_log_file = self._output_folder.joinpath(f"python_script.{job_arguments['java_gateway_port']}.log")
            self._toshi_api.automation_task.upload_task_file(task_id, pyth_log_file, 'WRITE')

            java_log_file = self._output_folder.joinpath(f"java_app.{job_arguments['java_gateway_port']}.log")
            self._toshi_api.automation_task.upload_task_file(task_id, java_log_file, 'WRITE')

            # get the predecessors
            source_solution_id = job_arguments.get('source_solution_id')
            predecessors = [dict(id=source_solution_id,depth=-1),]
            
            source_predecessors = self._toshi_api.get_predecessors(source_solution_id) 

            if source_predecessors:
                for predecessor in source_predecessors:
                    predecessor['depth'] += -1
                predecessors.append(predecessor)

            inversion_id = self._toshi_api.time_dependent_inversion_solution.upload_inversion_solution(task_id,
                filepath=output_file,
                source_solution_id=source_solution_id,
                predecessors=predecessors,
                meta=task_arguments)
            log.info(f"Saved time dependent inversion solution: {inversion_id}")


        t1 = dt.datetime.utcnow()
        log.info("Report took %s secs" % (t1-t0).total_seconds())


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

