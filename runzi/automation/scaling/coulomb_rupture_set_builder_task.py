import argparse
import csv
import datetime as dt
import json
import logging
import os
import platform
import pwd
import time
from pathlib import PurePath

import git
from dateutil.tz import tzutc
from nshm_toshi_client.general_task import GeneralTask
from nshm_toshi_client.rupture_generation_task import RuptureGenerationTask
from nshm_toshi_client.task_relation import TaskRelation
from py4j.java_gateway import GatewayParameters, JavaGateway

CLUSTER_MODE = os.getenv('NZSHM22_SCRIPT_CLUSTER_MODE', False)

API_URL = os.getenv('NZSHM22_TOSHI_API_URL', "http://127.0.0.1:5000/graphql")
API_KEY = os.getenv('NZSHM22_TOSHI_API_KEY', "")
S3_URL = os.getenv('NZSHM22_TOSHI_S3_URL', "http://localhost:4569")


class RuptureSetBuilderTask:
    """
    The python client for a RuptureSetBuildTask
    """

    def __init__(self, job_args):

        self.use_api = job_args.get('use_api', False)

        # setup the java gateway binding
        self._gateway = JavaGateway(gateway_parameters=GatewayParameters(port=job_args['java_gateway_port']))
        app = self._gateway.entry_point
        self._builder = app.getCoulombRuptureSetBuilder()

        repos = ["opensha", "nzshm-opensha", "nzshm-runzi"]
        self._output_folder = PurePath(
            job_args.get('working_path')
        )  # .joinpath('tmp').joinpath(dt.datetime.utcnow().isoformat().replace(':','-'))

        # setup the csv (backup) task recorder
        # self._repoheads = get_repo_heads(PurePath(job_args['root_folder']), repos)

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

    def run(self, task_arguments, job_arguments):

        # print(task_arguments)
        # print(job_arguments)

        t0 = dt.datetime.utcnow()

        environment = {
            "host": platform.node(),
            # "gitref_opensha":self._repoheads['opensha'],
            # "gitref_nzshm-opensha":self._repoheads['nzshm-opensha'],
            # "gitref_nzshm-runzi":self._repoheads['nzshm-runzi'],
            "java_threads": job_arguments["java_threads"],
            "proc_count": job_arguments["PROC_COUNT"],
            "jvm_heap_max": job_arguments["JVM_HEAP_MAX"],
        }

        if self.use_api:
            # create new task in toshi_api
            task_id = self._ruptgen_api.create_task(
                dict(created=dt.datetime.now(tzutc()).isoformat()), arguments=task_arguments, environment=environment
            )

            # link task tp the parent task
            self._task_relation_api.create_task_relation(job_arguments['general_task_id'], task_id)
            # #link task to the input datafile (*.XML)
            # self._ruptgen_api.link_task_file(task_id, crustal_id, 'READ')

        else:
            task_id = None

        # Run the task....
        ta = task_arguments

        assert self._builder
        print('Got RuptureSetBuilder: ', self._builder)

        self._builder.setMaxFaultSections(int(ta["max_sections"])).setMaxJumpDistance(
            float(ta["max_jump_distance"])
        ).setAdaptiveMinDist(float(ta["adaptive_min_distance"])).setAdaptiveSectFract(
            float(ta["thinning_factor"])
        ).setMinSubSectsPerParent(
            int(ta["min_sub_sects_per_parent"])
        ).setMinSubSections(
            int(ta["min_sub_sections"])
        ).setFaultModel(
            ta["fault_model"]
        )
        # .setCmlRakeThresh(0.0) #TURN IT OFF

        if "CFM_1_0" in ta['fault_model']:
            tvzDomain = "4"
            self._builder.setScaleDepthIncludeDomain(tvzDomain, ta['depth_scaling_tvz']).setScaleDepthExcludeDomain(
                tvzDomain, ta['depth_scaling_sans']
            )

        # invert_rake = bool(ta.get('use_inverted_rake', False))
        # if invert_rake:
        #     print('use inverted rake!')
        #     self._builder.setInvertRake(invert_rake)

        if ta.get('scaling_relationship') == "SIMPLE_CRUSTAL":
            sr = self._gateway.jvm.nz.cri.gns.NZSHM22.opensha.calc.SimplifiedScalingRelationship()
            sr.setupCrustal(4.2, 4.2)  # TODO this is hard-wired
            self._builder.setScalingRelationship(sr)
        elif ta.get('scaling_relationship') == "TMG_CRU_2017":
            sr = self._gateway.jvm.org.opensha.commons.calc.magScalingRelations.magScalingRelImpl.TMG2017CruMagAreaRel()
            sr.setRake(0.0)
            self._builder.setScalingRelationship(sr)

        # name the output file
        if self.use_api:
            outputfile = self._output_folder.joinpath(f"NZSHM22_RuptureSet-{task_id}.zip")
        else:
            outputfile = self._output_folder.joinpath(self._builder.getDescriptiveName() + ".zip")
        log.info("building %s started at %s" % (outputfile, dt.datetime.utcnow().isoformat()))

        self._builder.setNumThreads(int(job_arguments["java_threads"])).buildRuptureSet()

        # capture task metrics
        duration = (dt.datetime.utcnow() - t0).total_seconds()
        metrics = self.ruptureSetMetrics()

        # write the result
        self._builder.writeRuptureSet(str(outputfile))

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
            self._ruptgen_api.upload_task_file(task_id, outputfile, 'WRITE', meta=task_arguments)

            # and the log files, why not
            java_log_file = self._output_folder.joinpath(f"java_app.{job_arguments['java_gateway_port']}.log")
            self._ruptgen_api.upload_task_file(task_id, java_log_file, 'WRITE')
            pyth_log_file = self._output_folder.joinpath(f"python_script.{job_arguments['java_gateway_port']}.log")
            self._ruptgen_api.upload_task_file(task_id, pyth_log_file, 'WRITE')

        log.info("build took %s secs" % (dt.datetime.utcnow() - t0).total_seconds())


def get_repo_heads(rootdir, repos):
    result = {}
    for reponame in repos:
        repo = git.Repo(rootdir.joinpath(reponame))
        headcommit = repo.head.commit
        result[reponame] = headcommit.hexsha
    return result


if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO)

    loglevel = logging.INFO
    logging.getLogger('py4j.java_gateway').setLevel(loglevel)
    logging.getLogger('nshm_toshi_client.toshi_client_base').setLevel(loglevel)
    logging.getLogger('nshm_toshi_client.toshi_file').setLevel(loglevel)
    logging.getLogger('urllib3').setLevel(loglevel)
    logging.getLogger('git.cmd').setLevel(loglevel)

    log = logging.getLogger(__name__)

    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    args = parser.parse_args()

    config_file = args.config
    f = open(config_file, 'r', encoding='utf-8')
    config = json.load(f)

    # maybe the JVM App is a little slow to get listening
    time.sleep(3)
    if CLUSTER_MODE:

        # Wait for some more time, scaled by taskid to avoid S3 consistency issue
        time.sleep(config['job_arguments']['task_id'] * 5)

    # print(config)
    task = RuptureSetBuilderTask(config['job_arguments'])
    task.run(**config)
