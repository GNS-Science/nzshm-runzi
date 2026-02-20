import argparse
import datetime as dt
import json
import time
import urllib
import uuid
import zipfile
from pathlib import Path

from dateutil.tz import tzutc
from nshm_toshi_client.task_relation import TaskRelation  # TODO deprecate

try:
    from openquake.converters.ucerf.parsers.sections_geojson import get_multi_fault_source
    from openquake.hazardlib.sourcewriter import write_source_model
except ImportError:
    print("openquake not installed, not importing")

from pydantic import BaseModel

from runzi.arguments import SystemArgs, TaskLanguage
from runzi.automation.scaling.file_utils import download_files, get_output_file_id
from runzi.automation.scaling.local_config import API_KEY, API_URL, S3_URL, SPOOF, USE_API, WORK_PATH
from runzi.automation.scaling.toshi_api import ModelType, SubtaskType, ToshiApi

default_system_args = SystemArgs(
    task_language=TaskLanguage.PYTHON,
    use_api=USE_API,
    ecs_max_job_time_min=30,
    ecs_memory=30720,
    ecs_vcpu=4,
    ecs_job_definition="Fargate-runzi-opensha-JD",
    ecs_job_queue="BasicFargate_Q",
)


class OQConvertArgs(BaseModel):
    """Input for converting OpenSHA inversion to OpenQuake source."""

    source_solution_id: str
    investigation_time_years: float
    rupture_sampling_distance_km: float


class OQConvertTask:

    def __init__(self, user_args: OQConvertArgs, system_args: SystemArgs, model_type: ModelType):

        self.user_args = user_args
        self.system_args = system_args
        self.model_type = model_type
        self.use_api = system_args.use_api

        headers = {"x-api-key": API_KEY}
        self.toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
        self.task_relation_api = TaskRelation(API_URL, None, with_schema_validation=True, headers=headers)

    def convert(self, src_folder: Path) -> Path:

        # The `tectonic_region_type` label must be consistent with what you use in the
        # logic tree for the ground-motion characterisation
        # Use "Subduction Interface" or "Active Shallow Crust"
        # tectonic_region_type = "Subduction Interface"
        if self.model_type is ModelType.CRUSTAL:
            tectonic_region_type = "Active Shallow Crust"
        elif self.model_type is ModelType.SUBDUCTION:
            tectonic_region_type = "Subduction Interface"

        dip_sd = self.user_args.rupture_sampling_distance_km
        strike_sd = dip_sd
        source_id = self.user_args.source_solution_id.replace('=', '_')
        source_name = source_id
        investigation_time = self.user_args.investigation_time_years
        prefix = source_id

        computed = get_multi_fault_source(
            str(src_folder), dip_sd, strike_sd, source_id, source_name, tectonic_region_type, investigation_time, prefix
        )

        print(computed)

        out_file = WORK_PATH / f'{source_id}-ruptures.xml'
        write_source_model(
            str(out_file), [computed], name=source_name, investigation_time=investigation_time, prefix=prefix
        )

        # zip this and return the archive path
        # TODO: should we not archive the huge hdf5. I don't think it's needed, but this needs to be tested
        output_zip = Path(WORK_PATH, self.solution_archive_filename.replace('.zip', '_nrml.zip'))
        print(f'output: {output_zip}')
        zfile = zipfile.ZipFile(output_zip, 'w')
        for filename in list(WORK_PATH.glob(f'{source_id}*')):
            arcname = str(filename).replace(str(WORK_PATH), '')
            zfile.write(filename, arcname)
            print(f'archived {filename} as {arcname}')

        return output_zip

    def get_task_id(self):

        if self.use_api:
            # create new task in toshi_api
            task_id = self.toshi_api.automation_task.create_task(
                dict(
                    created=dt.datetime.now(tzutc()).isoformat(),
                    task_type=SubtaskType.SOLUTION_TO_NRML.name,
                    model_type=self.model_type.name.upper(),
                ),
                arguments=self.user_args.model_dump(mode='json'),
                environment={},
            )

            # link task to the parent task
            self.task_relation_api.create_task_relation(self.system_args.general_task_id, task_id)

            # link task to the input solution
            if self.user_args.source_solution_id:
                self.toshi_api.automation_task.link_task_file(task_id, self.user_args.source_solution_id, 'READ')
        else:
            task_id = str(uuid.uuid4())
        return task_id

    def get_source_solution(self) -> Path:
        file_generator = get_output_file_id(self.toshi_api, self.user_args.source_solution_id)  # for file by file ID
        solutions = download_files(self.toshi_api, file_generator, str(WORK_PATH), overwrite=False)
        input_solution_info = solutions[self.user_args.source_solution_id]
        src_folder = WORK_PATH / "downloads" / self.user_args.source_solution_id
        self.solution_archive_filename = input_solution_info['filepath']

        # get name of zifile like `NZSHM22_InversionSolution-QXV0b21hdGlvblRhc2s6MjQ4OVMycWNI.zip`
        with zipfile.ZipFile(self.solution_archive_filename, 'r') as zip_ref:
            zip_ref.extractall(src_folder)

        return src_folder

    def run(self):
        # Run the task....
        t0 = dt.datetime.now()

        task_id = self.get_task_id()

        # get the input solution file
        src_folder = self.get_source_solution()

        # DOIT
        if SPOOF:
            output_zip = Path(WORK_PATH, self.solution_archive_filename.replace('.zip', '_nrml.zip.spoof'))
            output_zip.touch()
        else:
            output_zip = self.convert(src_folder)

        t1 = dt.datetime.now()
        print("Conversion took %s secs" % (t1 - t0).total_seconds())

        if self.use_api:

            # get the predecessors
            predecessors = [
                dict(id=self.user_args.source_solution_id, depth=-1),
            ]
            source_predecessors = self.toshi_api.get_predecessors(self.user_args.source_solution_id)

            if source_predecessors:
                for predecessor in source_predecessors:
                    predecessor['depth'] += -1
                    predecessors.append(predecessor)

            nrml_id = self.toshi_api.inversion_solution_nrml.upload_inversion_solution_nrml(
                task_id,
                source_solution_id=self.user_args.source_solution_id,
                filepath=output_zip,
                predecessors=predecessors,
                meta=self.user_args.model_dump(mode='json'),
                metrics=None,
            )

            print("created nrml: ", nrml_id)

            done_args = {
                'task_id': task_id,
                'duration': (dt.datetime.now() - t0).total_seconds(),
                'result': "SUCCESS",
                'state': "DONE",
            }
            self.toshi_api.automation_task.complete_task(done_args, {})


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

    user_args = OQConvertArgs(**config['task_args'])
    system_args = SystemArgs(**config['task_system_args'])
    model_type = ModelType(config['model_type'])

    # Wait for some more time, scaled by taskid to avoid S3 consistency issue
    time.sleep(system_args.task_count)

    # print(config)
    task = OQConvertTask(user_args, system_args, model_type)
    task.run()
