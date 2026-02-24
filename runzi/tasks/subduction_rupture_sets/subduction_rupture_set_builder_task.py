import argparse
import datetime as dt
import json
import logging
import platform
import time
import urllib
from pathlib import Path, PurePath
from typing import Optional

import git
from dateutil.tz import tzutc
from nshm_toshi_client.general_task import GeneralTask
from nshm_toshi_client.rupture_generation_task import RuptureGenerationTask
from nshm_toshi_client.task_relation import TaskRelation
from py4j.java_gateway import GatewayParameters, JavaGateway
from pydantic import BaseModel

from runzi.arguments import SystemArgs, TaskLanguage
from runzi.automation.local_config import API_KEY, API_URL, S3_URL, SPOOF, USE_API, WORK_PATH

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

loglevel = logging.INFO
logging.getLogger('py4j.java_gateway').setLevel(loglevel)
logging.getLogger('nshm_toshi_client.toshi_client_base').setLevel(loglevel)
logging.getLogger('nshm_toshi_client.toshi_file').setLevel(loglevel)
logging.getLogger('urllib3').setLevel(loglevel)
logging.getLogger('git.cmd').setLevel(loglevel)

default_system_args = SystemArgs(
    task_language=TaskLanguage.JAVA,
    use_api=USE_API,
    java_threads=16,
    jvm_heap_max=32,
    ecs_max_job_time_min=60,
    ecs_memory=30720,
    ecs_vcpu=4,
    ecs_job_definition="Fargate-runzi-opensha-JD",
    ecs_job_queue="BasicFargate_Q",
)


class SubductionRuptureSetArgs(BaseModel):
    """Input for generating subduction rupture sets.
    
    For details on the parameters see
    https://github.com/GNS-Science/nzshm-opensha/blob/main/doc/NZSHM22-subduction-rupture-generation.md
    """

    fault_model: str
    min_aspect_ratio: float
    max_aspect_ratio: float
    aspect_depth_threshold: int
    """The depth (in sub-section tiles) below which the `max_aspect_ratio` will not be enforced."""

    min_fill_ratio: float
    """Prevents empty cells in subduction ruptures."""

    scaling_relationship: str
    slip_along_rupture_model: str
    ("""The slip function for the rupture."""
    """See https://github.com/opensha/opensha/blob/master/src/main/java/scratch/UCERF3/enumTreeBranches"""
    """/SlipAlongRuptureModels.java""")

    deformation_model: Optional[str] = None


class SubductionRuptureSetBuilderTask:
    """Class for building subduction rupture sets."""

    def __init__(self, user_args: SubductionRuptureSetArgs, system_args: SystemArgs):

        self.user_args = user_args
        self.system_args = system_args
        self.use_api = system_args.use_api

        # setup the java gateway binding
        gateway = JavaGateway(gateway_parameters=GatewayParameters(port=self.system_args.java_gateway_port))
        app = gateway.entry_point
        self.builder = app.getSubductionRuptureSetBuilder()

        self.output_folder = PurePath(WORK_PATH)

        if self.use_api:
            headers = {"x-api-key": API_KEY}
            self.ruptgen_api = RuptureGenerationTask(
                API_URL, S3_URL, None, with_schema_validation=True, headers=headers
            )
            self.general_api = GeneralTask(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
            self.task_relation_api = TaskRelation(API_URL, None, with_schema_validation=True, headers=headers)

    def ruptureSetMetrics(self):
        return dict(
            subsection_count=self.builder.getSubSections().size(), rupture_count=self.builder.getRuptures().size()
        )

    def run(self):

        t0 = dt.datetime.now()

        environment = {
            "host": platform.node(),
            "java_threads": self.system_args.java_threads,
            "proc_count": self.system_args.java_threads,
        }

        if self.use_api:
            task_id = self.ruptgen_api.create_task(
                dict(
                    created=dt.datetime.now(tzutc()).isoformat(),
                    task_type="RUPTURE_SET",
                    model_type="SUBDUCTION",
                ),
                arguments=self.user_args.model_dump(mode='json'),
                environment=environment,
            )

            # link task tp the parent task
            self.task_relation_api.create_task_relation(self.system_args.general_task_id, task_id)
        else:
            task_id = None

        if not self.builder:
            raise RuntimeError("Java Gateway could not get CoulombRuptureSetBuilder")
        print('Got RuptureSetBuilder: ', self.builder)

        self.builder.setDownDipAspectRatio(
            self.user_args.min_aspect_ratio, self.user_args.max_aspect_ratio, self.user_args.aspect_depth_threshold
        )
        self.builder.setDownDipMinFill(self.user_args.min_fill_ratio)
        self.builder.setScalingRelationship(self.user_args.scaling_relationship)
        self.builder.setSlipAlongRuptureModel(self.user_args.slip_along_rupture_model)
        self.builder.setFaultModel(self.user_args.fault_model)
        fault_models = [self.user_args.fault_model]

        if deformation_model := self.user_args.deformation_model:
            self.builder.setDeformationModel(deformation_model)

        # name the output file
        if self.use_api:
            outputfile = self.output_folder.joinpath(f"NZSHM22_RuptureSet-{task_id}.zip")
        else:
            outputfile = self.output_folder.joinpath(self.builder.getDescriptiveName() + ".zip")
        log.info("building %s started at %s" % (outputfile, dt.datetime.now().isoformat()))

        if SPOOF:
            metrics = {"subsection_count": 0, "rupture_count": 0}
            outputfile = outputfile.with_suffix('.spoof')
            Path(outputfile).touch()
        else:
            self.builder.setNumThreads(self.system_args.java_threads).buildRuptureSet()
            metrics = self.ruptureSetMetrics()
            self.builder.writeRuptureSet(str(outputfile))

        # capture task metrics
        duration = (dt.datetime.now() - t0).total_seconds()

        if self.use_api:
            done_args = {
                'task_id': task_id,
                'duration': duration,
                'result': "SUCCESS",
                'state': "DONE",
            }
            self.ruptgen_api.complete_task(done_args, metrics)

            # upload the task output
            self.ruptgen_api.upload_rupture_set(
                task_id,
                outputfile,
                fault_models,
                meta=self.user_args.model_dump(mode='json'),
                metrics=metrics,
            )

            # and the log files, why not
            java_log_file = self.output_folder.joinpath(f"java_app.{self.system_args.java_gateway_port}.log")
            self.ruptgen_api.upload_task_file(task_id, java_log_file, 'WRITE')
            # pyth_log_file = self._output_folder.joinpath(f"python_script.{job_arguments['java_gateway_port']}.log")
            # self._ruptgen_api.upload_task_file(task_id, pyth_log_file, 'WRITE')

        print("; took %s secs" % (dt.datetime.now() - t0).total_seconds())


def get_repo_heads(rootdir, repos):
    result = {}
    for reponame in repos:
        repo = git.Repo(rootdir.joinpath(reponame))
        headcommit = repo.head.commit
        result[reponame] = headcommit.hexsha
    return result


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

    # print(config)
    user_args = SubductionRuptureSetArgs(**config['task_args'])
    system_args = SystemArgs(**config['task_system_args'])
    task = SubductionRuptureSetBuilderTask(user_args, system_args)

    # maybe the JVM App is a little slow to get listening
    time.sleep(3)
    # Wait for some more time, scaled by taskid to avoid S3 consistency issue
    time.sleep(system_args.task_count)

    task.run()
