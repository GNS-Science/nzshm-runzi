import argparse
import datetime as dt
import json
import time
import urllib
import uuid
from pathlib import Path, PurePath
from typing import Any, Optional

from dateutil.tz import tzutc
from nshm_toshi_client.task_relation import TaskRelation
from pydantic import BaseModel
from solvis import InversionSolution

from runzi.arguments import SystemArgs, TaskLanguage
from runzi.automation.file_utils import download_files, get_output_file_id
from runzi.automation.local_config import API_KEY, API_URL, S3_URL, SPOOF, USE_API, WORK_PATH
from runzi.automation.toshi_api import ModelType, SubtaskType, ToshiApi

default_system_args = SystemArgs(
    task_language=TaskLanguage.PYTHON,
    use_api=USE_API,
    ecs_max_job_time_min=10,
    ecs_memory=30720,
    ecs_vcpu=4,
    ecs_job_definition="Fargate-runzi-opensha-JD",
    ecs_job_queue="BasicFargate_Q",
)


class ScaleSolutionArgs(BaseModel):
    """Input for scaling inversion solutions."""

    scale: float
    polygon_scale: float
    polygon_max_mag: float
    source_solution_id: str


class ScaleSolutionTask:
    """The python client for solution rate scaling."""

    def __init__(self, user_args: ScaleSolutionArgs, system_args: SystemArgs, model_type: ModelType):

        self.user_args = user_args
        self.system_args = system_args
        self.model_type = model_type
        self.use_api = system_args.use_api
        self.output_folder = WORK_PATH

        if self.use_api:
            headers = {"x-api-key": API_KEY}
            self.toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
            self.task_relation_api = TaskRelation(API_URL, None, with_schema_validation=True, headers=headers)

    def run(self):
        # Run the task....
        t0 = dt.datetime.now()

        file_generator = get_output_file_id(self.toshi_api, self.user_args.source_solution_id)
        source_solution_info = download_files(self.toshi_api, file_generator, str(WORK_PATH), overwrite=False)
        source_solution_filepath = source_solution_info[self.user_args.source_solution_id]['filepath']

        if self.use_api:
            # create new task in toshi_api
            task_id = self.toshi_api.automation_task.create_task(
                dict(
                    created=dt.datetime.now(tzutc()).isoformat(),
                    task_type=SubtaskType.SCALE_SOLUTION.name,
                    model_type=self.model_type.name.upper(),
                ),
                arguments=self.user_args.model_dump(mode='json'),
                environment={},
            )

            # link automation task to the parent general task
            self.task_relation_api.create_task_relation(self.system_args.general_task_id, task_id)

            # link task to the input solution
            self.toshi_api.automation_task.link_task_file(task_id, self.user_args.source_solution_id, 'READ')

        else:
            task_id = str(uuid.uuid4())

        # DO THE WORK
        if SPOOF:
            output_solution_filepath = Path(
                self.output_folder, 'NZSHM22_ScaledInversionSolution-' + str(task_id) + '.zip.spoof'
            )
            output_solution_filepath.touch()
            result = {
                'metrics': dict(scale=self.user_args.scale),
                'scaled_solution': str(output_solution_filepath),
            }
        else:
            result = self.scaleRuptureRates(
                source_solution_filepath,
                task_id,
                self.user_args.scale,
                self.user_args.polygon_scale,
                self.user_args.polygon_max_mag,
            )

        # SAVE the results
        if self.use_api:

            # record the complteded task
            done_args = {
                'task_id': task_id,
                'duration': (dt.datetime.now() - t0).total_seconds(),
                'result': "SUCCESS",
                'state': "DONE",
            }
            self.toshi_api.automation_task.complete_task(done_args, result['metrics'])

            # add the log files
            # pyth_log_file = self.output_folder.joinpath(f"python_script.{self.system_args.task_count}.log")
            # self.toshi_api.automation_task.upload_task_file(task_id, pyth_log_file, 'WRITE')

            # get the predecessors
            predecessors = [
                dict(id=self.user_args.source_solution_id, depth=-1),
            ]

            source_predecessors = self.toshi_api.get_predecessors(self.user_args.source_solution_id)
            print('source_predecessors', source_predecessors)

            if source_predecessors:
                for predecessor in source_predecessors:
                    print('pred:', predecessor)
                    predecessor['depth'] += -1
                    predecessors.append(predecessor)

            inversion_id = self.toshi_api.scaled_inversion_solution.upload_inversion_solution(
                task_id,
                filepath=result['scaled_solution'],
                source_solution_id=self.user_args.source_solution_id,
                predecessors=predecessors,
                meta=user_args.model_dump(mode='json'),
                metrics=result['metrics'],
            )
            print("created scaled inversion solution: ", inversion_id)

        t1 = dt.datetime.now()
        print("Report took %s secs" % (t1 - t0).total_seconds())

    def scaleRuptureRates(
        self,
        in_solution_filepath: str,
        task_id: str,
        scale: float,
        polygon_scale: Optional[float] = None,
        polygon_max_mag: Optional[float] = None,
    ) -> dict[str, Any]:

        soln = InversionSolution().from_archive(in_solution_filepath)

        rr = soln.ruptures
        ra = soln.rates
        ri = soln.indices
        ruptures = rr.copy()
        rates = ra.copy() * scale
        indices = ri.copy()

        # apply polygon rates
        if polygon_scale and polygon_max_mag:
            print('scale polygons')
            mag_ind = rr['Magnitude'] <= polygon_max_mag
            rates.loc[mag_ind, 'Annual Rate'] = rates[mag_ind]['Annual Rate'] * polygon_scale

        # all other props are derived from these
        scaled_soln = InversionSolution()
        scaled_soln.set_props(rates, ruptures, indices, soln.fault_sections.copy())

        new_archive = PurePath(self.output_folder, 'NZSHM22_ScaledInversionSolution-' + str(task_id) + '.zip')

        scaled_soln.to_archive(new_archive, in_solution_filepath)

        metrics = dict(scale=scale)
        return dict(scaled_solution=new_archive, metrics=metrics)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    args = parser.parse_args()

    try:
        # LOCAL and CLUSTER this is a file
        config_file = args.config
        f = open(args.config, 'r', encoding='utf-8')
        config = json.load(f)
    except FileNotFoundError:
        # for AWS this must be a quoted JSON string
        config = json.loads(urllib.parse.unquote(args.config))

    user_args = ScaleSolutionArgs(**config['task_args'])
    system_args = SystemArgs(**config['task_system_args'])
    model_type = ModelType(config['model_type'])

    # Wait for some more time, scaled by taskid to avoid S3 consistency issue
    time.sleep(system_args.task_count)

    # print(config)
    task = ScaleSolutionTask(user_args, system_args, model_type)
    task.run()
