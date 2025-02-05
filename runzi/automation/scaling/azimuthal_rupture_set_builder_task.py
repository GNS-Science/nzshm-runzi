import argparse
import datetime as dt
import json
import os
import platform
import time
from pathlib import PurePath

import git
from dateutil.tz import tzutc
from nshm_toshi_client.general_task import GeneralTask
from nshm_toshi_client.rupture_generation_task import RuptureGenerationTask
from nshm_toshi_client.task_relation import TaskRelation
from py4j.java_gateway import GatewayParameters, JavaGateway

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
        gateway = JavaGateway(gateway_parameters=GatewayParameters(port=job_args['java_gateway_port']))
        app = gateway.entry_point
        self._builder = app.getAzimuthalRuptureSetBuilder()

        # get the root path for the task local data
        # root_folder = PurePath(os.getcwd())

        repos = ["opensha", "nshm-nz-opensha"]
        # repo_root = root_folder
        self._output_folder = PurePath(
            job_args.get('working_path')
        )  # .joinpath('tmp').joinpath(dt.datetime.utcnow().isoformat().replace(':','-'))
        # os.mkdir(self._output_folder)

        # setup the csv (backup) task recorder
        self._writer = None  # CSVResultWriter(open(self._output_folder.joinpath('results.csv'), 'w'), repos)
        self._repoheads = get_repo_heads(PurePath(job_args['root_folder']), repos)

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
        # metrics["possible_cluster_connections"] = conf.getConnectionStrategy().getClusterConnectionCount()

        # # get info from the configuratiion
        conf = self._builder.getPlausibilityConfig()
        conf_diags = json.loads(conf.toJSON())
        conns = 0
        for cluster in conf_diags['connectionStrategy']['clusters']:
            conns += len(cluster.get('connections', []))
        metrics["cluster_connections"] = conns

        return metrics

    def run(self, task_arguments, job_arguments):

        # print(task_arguments)
        # print(job_arguments)

        t0 = dt.datetime.utcnow()

        environment = {
            "host": platform.node(),
            "gitref_opensha": self._repoheads['opensha'],
            "gitref_nshm-nz-opensha": self._repoheads['nshm-nz-opensha'],
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
        ## for crustal
        self._builder.setMaxFaultSections(int(ta["max_sections"])).setMaxJumpDistance(
            float(ta["max_jump_distance"])
        ).setPermutationStrategy(ta["connection_strategy"]).setMaxSubSectionLength(
            float(ta["down_dip_width"])
        ).setMinSubSectsPerParent(
            int(ta["min_sub_sects_per_parent"])
        ).setMinSubSections(
            int(ta["min_sub_sections"])
        ).setMaxCumulativeAzimuthChange(
            float(ta["max_cumulative_azimuth"])
        ).setThinningFactor(
            float(ta["thinning_factor"])
        ).setFaultModel(
            ta["fault_model"]
        )

        # name the output file
        outputfile = self._output_folder.joinpath(self._builder.getDescriptiveName() + ".zip")
        print("building %s started at %s" % (outputfile, dt.datetime.utcnow().isoformat()), end=' ')

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

        print("; took %s secs" % (dt.datetime.utcnow() - t0).total_seconds())


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

    config_file = args.config
    f = open(config_file, 'r', encoding='utf-8')
    config = json.load(f)

    # maybe the JVM App is a little slow to get listening
    time.sleep(5)
    # Wait for some more time, scaled by taskid to avoid S3 consistency issue
    time.sleep(config['job_arguments']['task_id'] * 5)

    # print(config)
    task = RuptureSetBuilderTask(config['job_arguments'])
    task.run(**config)
