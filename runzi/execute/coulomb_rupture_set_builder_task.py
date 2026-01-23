import argparse
import datetime as dt
import json
import logging
import platform
import time
from typing_extensions import Self
from typing import Optional
import urllib
from pathlib import Path, PurePath
from zipfile import ZipFile

import git
from dateutil.tz import tzutc
from nshm_toshi_client.general_task import GeneralTask
from nshm_toshi_client.rupture_generation_task import RuptureGenerationTask
from nshm_toshi_client.task_relation import TaskRelation
from py4j.java_gateway import GatewayParameters, JavaGateway
from pydantic import BaseModel, model_validator

from runzi.automation.scaling.file_utils import download_files, get_output_file_id
from runzi.automation.scaling.local_config import API_KEY, API_URL, S3_URL, SPOOF_RUPTURESET, WORK_PATH
from runzi.automation.scaling.toshi_api import ModelType, ToshiApi
from runzi.execute.arguments import ArgBase, SystemArgs
from runzi.execute.utils import generate_automation_task_args

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

loglevel = logging.INFO
logging.getLogger('py4j.java_gateway').setLevel(loglevel)
logging.getLogger('nshm_toshi_client.toshi_client_base').setLevel(loglevel)
logging.getLogger('nshm_toshi_client.toshi_file').setLevel(loglevel)
logging.getLogger('urllib3').setLevel(loglevel)
logging.getLogger('git.cmd').setLevel(loglevel)


def get_fault_model_file(fault_model_file_id) -> Path:
    headers = {"x-api-key": API_KEY}
    toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
    file_generator = get_output_file_id(toshi_api, fault_model_file_id)
    fault_model_file_info = download_files(toshi_api, file_generator, str(WORK_PATH), overwrite=False)
    fault_model_archive_file_path = fault_model_file_info[fault_model_file_id]['filepath']
    with ZipFile(fault_model_archive_file_path, 'r') as archive:
        namelist = archive.namelist()
        if len(namelist) != 1:
            raise Exception("fault model archive should have exactly one file.")
        fault_model_file = namelist[0]
        archive.extract(fault_model_file, path=(Path(fault_model_archive_file_path).parent))
    return Path(fault_model_archive_file_path).parent / fault_model_file


class CoulombRuptureSetArgs(ArgBase):
    """Input for generating Coulomb rupture sets."""

    class DepthScaling(BaseModel):
        tvz: float
        sans: float

    class FaultModelFile(BaseModel):
        tag: str
        archive_id: str

    max_sections: int
    max_jump_distance: float
    adaptive_min_distance: float
    thinning_factor: float
    min_sub_sects_per_parent: int
    min_sub_sections: int
    scaling_relationship: str
    depth_scaling: Optional[DepthScaling] = None
    fault_model: Optional[str] = None
    fault_model_file: Optional[FaultModelFile] = None
    named_faults_file: Optional[FaultModelFile] = None

    @model_validator(mode='after')
    def _check_fault_model(self) -> Self:
        """Must specify either fault_model or fault_model_file"""
        has_fault_model = bool(self.fault_model)
        has_fault_model_file = bool(self.fault_model_file)
        if not (has_fault_model != has_fault_model_file):
            raise ValueError("Must specify fault_model or fault_model_file, not both")
        return self


class RuptureSetBuilderTask:
    """
    The python client for a RuptureSetBuildTask
    """

    def __init__(self, user_args: CoulombRuptureSetArgs, system_args: SystemArgs):

        self.user_args = user_args
        self.system_args = system_args
        self.use_api = system_args.use_api

        # setup the java gateway binding
        self._gateway = JavaGateway(gateway_parameters=GatewayParameters(port=self.system_args.java_gateway_port))
        app = self._gateway.entry_point
        self._builder = app.getCoulombRuptureSetBuilder()

        self._output_folder = PurePath(WORK_PATH)

        if self.use_api:
            headers = {"x-api-key": API_KEY}
            self._ruptgen_api = RuptureGenerationTask(
                API_URL, S3_URL, None, with_schema_validation=True, headers=headers
            )
            self._general_api = GeneralTask(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
            self._task_relation_api = TaskRelation(API_URL, None, with_schema_validation=True, headers=headers)

    def ruptureSetMetrics(self):
        metrics = {}
        metrics["subsection_count"] = self._builder.getSubSections().size()
        metrics["rupture_count"] = self._builder.getRuptures().size()
        return metrics

    def run(self):

        t0 = dt.datetime.now()

        environment = {
            "host": platform.node(),
            # "gitref_opensha":self._repoheads['opensha'],
            # "gitref_nzshm-opensha":self._repoheads['nzshm-opensha'],
            # "gitref_nzshm-runzi":self._repoheads['nzshm-runzi'],
            "java_threads": self.system_args.java_threads,
            "proc_count": self.system_args.java_threads,
            # "jvm_heap_max": self.system_args.jvm_heap_max,
        }

        if self.use_api:
            # create new task in toshi_api
            task_id = self._ruptgen_api.create_task(
                dict(
                    created=dt.datetime.now(tzutc()).isoformat(),
                    task_type="RUPTURE_SET",
                    model_type="CRUSTAL",
                ),
                arguments=self.user_args.model_dump(mode='json'),
                environment=environment,
            )

            # link task tp the parent task
            self._task_relation_api.create_task_relation(self.system_args.general_task_id, task_id)

        else:
            task_id = None

        # Run the task....
        if not self._builder:
            raise RuntimeError("Java Gateway could not get CoulombRuptureSetBuilder")
        print('Got RuptureSetBuilder: ', self._builder)

        max_sections = self.user_args.max_sections
        max_jump_distance = self.user_args.max_jump_distance
        adaptive_min_distance = self.user_args.adaptive_min_distance
        thinning_factor = self.user_args.thinning_factor
        min_sub_sects_per_parent = self.user_args.min_sub_sects_per_parent
        min_sub_sections = self.user_args.min_sub_sections
        fault_model = self.user_args.fault_model
        fault_model_file = self.user_args.fault_model_file
        named_faults_file = self.user_args.named_faults_file

        self._builder.setMaxFaultSections(max_sections)
        self._builder.setMaxJumpDistance(max_jump_distance)
        self._builder.setAdaptiveMinDist(adaptive_min_distance)
        self._builder.setAdaptiveSectFract(thinning_factor)
        self._builder.setMinSubSectsPerParent(min_sub_sects_per_parent)
        self._builder.setMinSubSections(min_sub_sections)

        if fault_model is not None:
            fault_models = [fault_model]
            self._builder.setFaultModel(fault_model)
        else:
            fault_models = [fault_model_file.archive_id]
            fault_model_file = get_fault_model_file(fault_model_file.archive_id)
            self._builder.setFaultModelFile(str(fault_model_file))

        if named_faults_file is not None:
            named_faults_file = get_fault_model_file(named_faults_file.archive_id)
            self._builder.setNamedFaultsFile(str(named_faults_file))

        # if "CFM_1_0" in fault_model:
        if self.user_args.depth_scaling is not None:
            tvzDomain = "4"
            depth_scaling_tvz = self.user_args.depth_scaling.tvz
            depth_scaling_sans = self.user_args.depth_scaling.sans
            self._builder.setScaleDepthIncludeDomain(tvzDomain, depth_scaling_tvz).setScaleDepthExcludeDomain(
                tvzDomain, depth_scaling_sans
            )

        # invert_rake = bool(ta.get('use_inverted_rake', False))
        # if invert_rake:
        #     print('use inverted rake!')
        #     self._builder.setInvertRake(invert_rake)
        scaling_relationship = self.user_args.scaling_relationship

        if scaling_relationship == "SIMPLE_CRUSTAL":
            sr = self._gateway.jvm.nz.cri.gns.NZSHM22.opensha.calc.SimplifiedScalingRelationship()
            sr.setupCrustal(4.2, 4.2)  # TODO this is hard-wired
            self._builder.setScalingRelationship(sr)
        elif scaling_relationship == "TMG_CRU_2017":
            sr = self._gateway.jvm.org.opensha.commons.calc.magScalingRelations.magScalingRelImpl.TMG2017CruMagAreaRel()
            sr.setRake(0.0)
            self._builder.setScalingRelationship(sr)
        else:
            raise ValueError(f"Unsupported scaling relationship: {scaling_relationship}")

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
            # record the completed task
            done_args = {
                'task_id': task_id,
                'duration': duration,
                'result': "SUCCESS",
                'state': "DONE",
            }
            self._ruptgen_api.complete_task(done_args, metrics)

            # upload the task output
            self._ruptgen_api.upload_rupture_set(
                task_id,
                outputfile,
                fault_models,
                meta=self.user_args.model_dump(mode='json'),
                metrics=metrics,
            )

            # and the log files, why not
            java_log_file = self._output_folder.joinpath(f"java_app.{self.system_args.java_gateway_port}.log")
            self._ruptgen_api.upload_task_file(task_id, java_log_file, 'WRITE')
            # pyth_log_file = self._output_folder.joinpath(f"python_script.{job_arguments['java_gateway_port']}.log")
            # self._ruptgen_api.upload_task_file(task_id, pyth_log_file, 'WRITE')

        log.info("build took %s secs" % (dt.datetime.now() - t0).total_seconds())


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
    user_args = CoulombRuptureSetArgs(**config['task_args'])
    system_args = SystemArgs(**config['task_system_args'])
    task = RuptureSetBuilderTask(user_args, system_args)

    # maybe the JVM App is a little slow to get listening
    time.sleep(3)
    # Wait for some more time, scaled by taskid to avoid S3 consistency issue
    time.sleep(system_args.task_count)

    task.run()
