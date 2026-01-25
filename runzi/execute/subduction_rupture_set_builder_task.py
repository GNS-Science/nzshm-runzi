import argparse
from pathlib import Path
from typing import Optional
import urllib
import datetime as dt
import json
import os
import platform
import time
from pathlib import PurePath
import logging

import git
from dateutil.tz import tzutc
from nshm_toshi_client.general_task import GeneralTask
from nshm_toshi_client.rupture_generation_task import RuptureGenerationTask
from nshm_toshi_client.task_relation import TaskRelation
from py4j.java_gateway import GatewayParameters, JavaGateway
from runzi.automation.scaling.local_config import API_KEY, API_URL, S3_URL, SPOOF_RUPTURESET, WORK_PATH

from runzi.execute.arguments import ArgBase, SystemArgs

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

loglevel = logging.INFO
logging.getLogger('py4j.java_gateway').setLevel(loglevel)
logging.getLogger('nshm_toshi_client.toshi_client_base').setLevel(loglevel)
logging.getLogger('nshm_toshi_client.toshi_file').setLevel(loglevel)
logging.getLogger('urllib3').setLevel(loglevel)
logging.getLogger('git.cmd').setLevel(loglevel)

class SubductionRuptureSetArgs(ArgBase):
    """Input for generating subduction rupture sets."""

    fault_model: str
    min_aspect_ratio: float
    max_aspect_ratio: float
    aspect_depth_threshold: int
    min_fill_ratio: float
    growth_position_epsilon: float
    growth_size_epsilon: float
    scaling_relationship: str
    slip_along_rupture_model: str
    deformation_model: Optional[str]

class RuptureSetBuilderTask:
    """
    The python client for a RuptureSetBuildTask
    """

    def __init__(self, user_args: SubductionRuptureSetArgs, system_args: SystemArgs):

        self.user_args = user_args
        self.system_args = system_args
        self.use_api = system_args.use_api

        # setup the java gateway binding
        gateway = JavaGateway(gateway_parameters=GatewayParameters(port=self.system_args.java_gateway_port))
        app = gateway.entry_point
        self._builder = app.getSubductionRuptureSetBuilder()

        self._output_folder = PurePath(WORK_PATH)

        if self.use_api:
            headers = {"x-api-key": API_KEY}
            self._ruptgen_api = RuptureGenerationTask(
                API_URL, S3_URL, None, with_schema_validation=True, headers=headers
            )
            self._general_api = GeneralTask(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
            self._task_relation_api = TaskRelation(API_URL, None, with_schema_validation=True, headers=headers)

    def ruptureSetMetrics(self):
        return dict(
            subsection_count = self._builder.getSubSections().size(),
            rupture_count = self._builder.getRuptures().size()
        )

    def run(self, task_arguments, job_arguments):

        t0 = dt.datetime.now()

        environment = {
            "host": platform.node(),
            "java_threads": self.system_args.java_threads,
            "proc_count": self.system_args.java_threads,
        }

        if self.use_api:
            task_id = self._ruptgen_api.create_task(
                dict(
                    created=dt.datetime.now(tzutc()).isoformat(),
                    task_type="RUPTURE_SET",
                    model_type="SUBDUCTION",
                ),
                arguments=self.user_args.model_dump(mode='json'),
                environment=environment,
            )

            # link task tp the parent task
            self._task_relation_api.create_task_relation(self.system_args.general_task_id, task_id)
        else:
            task_id = None

        if not self._builder:
            raise RuntimeError("Java Gateway could not get CoulombRuptureSetBuilder")
        print('Got RuptureSetBuilder: ', self._builder)

        self._builder.setDownDipAspectRatio(self.user_args.min_aspect_ratio, self.user_args.max_aspect_ratio, self.user_args.aspect_depth_threshold)
        self._builder.setDownDipMinFill(self.user_args.min_fill_ratio)
        self._builder.setDownDipPositionCoarseness(self.user_args.growth_position_epsilon)
        self._builder.setDownDipSizeCoarseness(self.user_args.growth_size_epsilon)
        self._builder.setScalingRelationship(self.user_args.scaling_relationship)
        self._builder.setSlipAlongRuptureModel(self.user_args.slip_along_rupture_model)
        self._builder.setFaultModel(self.user_args.fault_model)

        if deformation_model := self.user_args.deformation_model:
            self._builder.setDeformationModel(deformation_model)

        # name the output file
        if self.use_api:
            outputfile = self._output_folder.joinpath(f"NZSHM22_RuptureSet-{task_id}.zip")
        else:
            outputfile = self._output_folder.joinpath(self._builder.getDescriptiveName() + ".zip")
        log.info("building %s started at %s" % (outputfile, dt.datetime.now().isoformat()))

        if not SPOOF_RUPTURESET:
            self._builder.setNumThreads(self.system_args.java_threads).buildRuptureSet()
            metrics = self.ruptureSetMetrics()
        else:
            metrics = {"subsection_count": 0, "rupture_count": 0}

        # capture task metrics
        duration = (dt.datetime.now() - t0).total_seconds()

        # write the result
        if not SPOOF_RUPTURESET:
            self._builder.writeRuptureSet(str(outputfile))
        else:
            Path(outputfile).touch()

        if self.use_api:
            done_args = {
                'task_id': task_id,
                'duration': duration,
                'result': "SUCCESS",
                'state': "DONE",
            }
            self._ruptgen_api.complete_task(done_args, metrics)

            # upload the task output
            self._ruptgen_api.upload_task_file(task_id, outputfile, 'WRITE', meta=task_arguments)

            # and the log files, why not
            java_log_file = self._output_folder.joinpath(f"java_app.{self.system_args.java_gateway_port}.log")
            self._ruptgen_api.upload_task_file(task_id, java_log_file, 'WRITE')
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
    task = RuptureSetBuilderTask(user_args, system_args)

    # maybe the JVM App is a little slow to get listening
    time.sleep(3)
    # Wait for some more time, scaled by taskid to avoid S3 consistency issue
    time.sleep(system_args.task_count)

    task.run()
