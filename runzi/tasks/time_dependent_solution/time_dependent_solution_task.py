import datetime as dt
import logging
import time
import uuid
from pathlib import Path

from dateutil.tz import tzutc
from nshm_toshi_client.task_relation import TaskRelation
from py4j.java_gateway import GatewayParameters, JavaGateway
from pydantic import BaseModel

from runzi.arguments import SystemArgs, TaskLanguage
from runzi.automation.file_utils import download_files, get_output_file_id
from runzi.automation.local_config import API_KEY, API_URL, S3_URL, SPOOF, USE_API, WORK_PATH
from runzi.automation.toshi_api import ModelType, SubtaskType, ToshiApi
from runzi.tasks.get_config import get_config

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

default_system_args = SystemArgs(
    task_language=TaskLanguage.JAVA,
    use_api=USE_API,
    java_threads=16,
    jvm_heap_max=32,
    ecs_max_job_time_min=10,
    ecs_memory=30720,
    ecs_vcpu=4,
    ecs_job_definition="Fargate-runzi-opensha-JD",
    ecs_job_queue="BasicFargate_Q",
)


class TimeDependentSolutionArgs(BaseModel):
    """Input for time dependent solution rate scaling."""

    source_solution_id: str
    current_year: int
    most_recent_event_enum: str
    aperiodicity: str
    forecast_timespan: int


class TimeDependentSolutionTask:
    """The python client for time dependent rate scaling."""

    def __init__(self, user_args: TimeDependentSolutionArgs, system_args: SystemArgs, model_type: ModelType):

        self.use_api = system_args.use_api
        self.output_folder = WORK_PATH
        self.system_args = system_args
        self.user_args = user_args
        self.model_type = model_type

        # setup the java gateway binding
        self.gateway = JavaGateway(gateway_parameters=GatewayParameters(port=self.system_args.java_gateway_port))
        self.time_dependent_generator = self.gateway.entry_point.getTimeDependentRatesGenerator()

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
                    task_type=SubtaskType.TIME_DEPENDENT_SOLUTION.name,
                    model_type=self.model_type.name,
                ),
                arguments=self.user_args.model_dump(mode='json'),
                environment={},
            )

            # link automation task to the parent general task
            self.task_relation_api.create_task_relation(self.system_args.general_task_id, task_id)

            # link task to the input solution
            input_file_id = self.user_args.source_solution_id
            if input_file_id:
                self.toshi_api.automation_task.link_task_file(task_id, input_file_id, 'READ')

        else:
            task_id = str(uuid.uuid4())

        output_file = str(self.output_folder / f"NZSHM22_TimeDependentInversionSolution-{task_id}.zip")
        self.time_dependent_generator.setSolutionFileName(source_solution_filepath)
        self.time_dependent_generator.setCurrentYear(self.user_args.current_year)
        self.time_dependent_generator.setMREData(self.user_args.most_recent_event_enum)
        self.time_dependent_generator.setAperiodicity(self.user_args.aperiodicity)
        self.time_dependent_generator.setForecastTimespan(self.user_args.forecast_timespan)
        self.time_dependent_generator.setOutputFileName(output_file)

        if SPOOF:
            output_file = str(Path(output_file).with_suffix('.spoof'))
            Path(output_file).touch()
        else:
            self.time_dependent_generator.generate()
            log.info(f'Produced file : {output_file}')

        t1 = dt.datetime.now()
        log.info("TimeDependent rates generation took %s secs" % (t1 - t0).total_seconds())

        # SAVE the results
        if self.use_api:

            # record the complteded task
            done_args = {
                'task_id': task_id,
                'duration': (dt.datetime.now() - t0).total_seconds(),
                'result': "SUCCESS",
                'state': "DONE",
            }
            self.toshi_api.automation_task.complete_task(done_args)

            # add the log files
            # pyth_log_file = self.output_folder.joinpath(f"python_script.{self.system_args.java_gateway_port}.log")
            # self.toshi_api.automation_task.upload_task_file(task_id, pyth_log_file, 'WRITE')

            java_log_file = self.output_folder.joinpath(f"java_app.{self.system_args.java_gateway_port}.log")
            self.toshi_api.automation_task.upload_task_file(task_id, java_log_file, 'WRITE')

            # get the predecessors
            predecessors = [
                dict(id=self.user_args.source_solution_id, depth=-1),
            ]

            source_predecessors = self.toshi_api.get_predecessors(self.user_args.source_solution_id)

            if source_predecessors:
                for predecessor in source_predecessors:
                    predecessor['depth'] += -1
                predecessors.append(predecessor)

            inversion_id = self.toshi_api.time_dependent_inversion_solution.upload_inversion_solution(
                task_id,
                filepath=output_file,
                source_solution_id=self.user_args.source_solution_id,
                predecessors=predecessors,
                meta=self.user_args.model_dump(mode='json'),
            )
            log.info(f"Saved time dependent inversion solution: {inversion_id}")

        t1 = dt.datetime.now()
        log.info("Report took %s secs" % (t1 - t0).total_seconds())


if __name__ == "__main__":

    config = get_config()

    user_args = TimeDependentSolutionArgs(**config['task_args'])
    system_args = SystemArgs(**config['task_system_args'])
    model_type = ModelType(config['model_type'])

    # maybe the JVM App is a little slow to get listening
    time.sleep(3)
    # Wait for some more time, scaled by taskid to avoid S3 consistency issue
    time.sleep(system_args.task_count)

    # print(config)
    task = TimeDependentSolutionTask(user_args, system_args, model_type)
    task.run()
