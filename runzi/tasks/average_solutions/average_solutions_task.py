import argparse
import base64
import datetime as dt
import json
import time
import urllib
import uuid
from itertools import chain
from pathlib import Path, PurePath

from dateutil.tz import tzutc
from nshm_toshi_client.task_relation import TaskRelation
from pydantic import BaseModel
from solvis import InversionSolution

from runzi.arguments import SystemArgs, TaskLanguage
from runzi.automation.scaling.file_utils import download_files, get_output_file_id
from runzi.automation.scaling.local_config import API_KEY, API_URL, S3_URL, SPOOF, USE_API, WORK_PATH
from runzi.automation.scaling.toshi_api import ModelType, SubtaskType, ToshiApi

default_system_args = SystemArgs(
    task_language=TaskLanguage.PYTHON,
    use_api=USE_API,
    ecs_max_job_time_min=10,
    ecs_memory=30720,
    ecs_vcpu=4,
    ecs_job_definition="Fargate-runzi-opensha-JD",
    ecs_job_queue="BasicFargate_Q",
)


class AverageSolutionsArgs(BaseModel):
    """Input for averaging solutions."""

    source_solution_ids: list[str]


def get_common_rupture_set(source_solution_ids: list[str], toshi_api: ToshiApi) -> str:

    rupture_set_id = ''
    for source_solution_id in source_solution_ids:

        new_rupture_set_id = get_rupture_set_id(source_solution_id, toshi_api)
        if not rupture_set_id:
            rupture_set_id = new_rupture_set_id
        else:
            if new_rupture_set_id == rupture_set_id:
                continue
            else:
                raise Exception(f'source objects {source_solution_ids} do not have consistant rupture sets')

    return rupture_set_id


def get_rupture_set_id(source_solution_id: str, toshi_api: ToshiApi) -> str:

    # I'm going to assume we can always use predecessors,
    # it should always be the case in the future and backwards
    # compatability is a bit of a pain to write

    rupture_set_id = get_rupture_set_from_predecessors(source_solution_id, toshi_api)

    if not rupture_set_id:
        raise Exception(f'cannot find rupture set for {source_solution_id}')

    return rupture_set_id


def get_rupture_set_from_predecessors(source_solution_id: str, toshi_api: ToshiApi) -> str:

    rupture_set_id = ''

    # it's possible there are multiple oldest predecessors (if for some reason the user is
    # calculating the average of average), so check them all
    # I'm assuming that if typename is 'File' then the object is a rupture set
    predecessors = toshi_api.get_predecessors(source_solution_id)

    if predecessors:
        oldest_depth = min([pred['depth'] for pred in predecessors])
        oldest_ids = [pred['id'] for pred in predecessors if pred['depth'] == oldest_depth]

        for id in oldest_ids:
            if (is_rupture_set(id)) and (not rupture_set_id):
                rupture_set_id = id
            elif is_rupture_set(id):
                if rupture_set_id == id:
                    continue
                else:
                    raise Exception(f'object with ID {source_solution_id} comes from multiple rupture sets')

    return rupture_set_id


def is_rupture_set(file_id: str) -> bool:
    return "'File:" in str(base64.b64decode(file_id))


class AverageSolutionsTask:
    """The python client for solution rate averaging."""

    def __init__(self, user_args: AverageSolutionsArgs, system_args: SystemArgs, model_type: ModelType):

        self.user_args = user_args
        self.system_args = system_args
        self.use_api = system_args.use_api
        self.output_folder = WORK_PATH
        self.model_type = model_type

        headers = {"x-api-key": API_KEY}
        self.toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
        self.task_relation_api = TaskRelation(API_URL, None, with_schema_validation=True, headers=headers)

    def run(self):

        t0 = dt.datetime.now()

        environment = {}
        source_solution_ids = self.user_args.source_solution_ids

        if self.use_api:
            # create new task in toshi_api
            task_id = self.toshi_api.automation_task.create_task(
                dict(
                    created=dt.datetime.now(tzutc()).isoformat(),
                    task_type=SubtaskType.AGGREGATE_SOLUTION.name,
                    model_type=self.model_type.name,
                ),
                arguments=self.user_args.model_dump(mode='json'),
                environment=environment,
            )

            # link automation task to the parent general task
            self.task_relation_api.create_task_relation(self.system_args.general_task_id, task_id)

        else:
            task_id = str(uuid.uuid4())

        # download the files
        common_rupture_set = get_common_rupture_set(source_solution_ids, self.toshi_api)

        file_generators = []
        for input_id in source_solution_ids:
            file_generators.append(get_output_file_id(self.toshi_api, input_id))  # for file by file ID

        source_solutions = download_files(
            self.toshi_api,
            chain(*file_generators),
            str(WORK_PATH),
            overwrite=False,
        )
        soln_filepaths = [soln['filepath'] for soln in source_solutions.values()]

        # DO THE WORK
        if SPOOF:
            new_archive = Path(WORK_PATH, 'NZSHM22_AveragedInversionSolution-' + str(task_id) + '.zip.spoof')
            new_archive.touch()
            metrics = dict(num_input_solns=0)
            result = dict(averaged_solution=new_archive, metrics=metrics)
        else:
            result = self.averageRuptureRates(soln_filepaths, task_id)

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
            # pyth_log_file = self._output_folder.joinpath(f"python_script.{self.system_args.task_count}.log")
            # self._toshi_api.automation_task.upload_task_file(task_id, pyth_log_file, 'WRITE')

            # get the predecessors
            predecessors = []
            for source_solution_id in source_solution_ids:
                predecessors.append(dict(id=source_solution_id, depth=-1))
                source_predecessors = self.toshi_api.get_predecessors(source_solution_id)

                if source_predecessors:
                    for predecessor in source_predecessors:
                        predecessor['depth'] += -1
                        predecessors.append(predecessor)

            meta = self.user_args.model_dump(mode='json')
            meta['source_solution_ids'] = source_solution_ids
            inversion_id = self.toshi_api.aggregate_inversion_solution.upload_inversion_solution(
                task_id,
                filepath=result['averaged_solution'],
                source_solution_ids=source_solution_ids,
                aggregation_fn='MEAN',
                common_rupture_set=common_rupture_set,
                predecessors=predecessors,
                meta=meta,
                metrics=result['metrics'],
            )
            print("created averaged inversion solution: ", inversion_id)

        t1 = dt.datetime.now()
        print("Report took %s secs" % (t1 - t0).total_seconds())

    def averageRuptureRates(self, in_solution_filepaths, task_id):
        raise NotImplementedError("uses old solvis API")

        for i, in_solution_filepath in enumerate(in_solution_filepaths):
            soln = InversionSolution().from_archive(in_solution_filepath)
            if i == 0:
                rr = soln.ruptures
                ra = soln.rates
                ri = soln.indices
                ruptures = rr.copy()
                rates = ra.copy()
                indices = ri.copy()
                fault_sections = soln.fault_sections.copy()
            else:
                rates += soln.rates
        rates = rates / len(in_solution_filepaths)

        scaled_soln = InversionSolution()  # noqa: F405
        scaled_soln.set_props(rates, ruptures, indices, fault_sections)

        new_archive = PurePath(WORK_PATH, 'NZSHM22_AveragedInversionSolution-' + str(task_id) + '.zip')

        # scaled_soln.to_archive(new_archive, in_solution_filepath)
        metrics = dict(num_input_solns=len(in_solution_filepaths))
        return dict(averaged_solution=new_archive, metrics=metrics)


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

    user_args = AverageSolutionsArgs(**config['task_args'])
    system_args = SystemArgs(**config['task_system_args'])
    model_type = ModelType(config['model_type'])

    # Wait for some more time, scaled by taskid to avoid S3 consistency issue
    time.sleep(system_args.task_count)

    # print(config)
    task = AverageSolutionsTask(user_args, system_args, model_type)
    task.run()
