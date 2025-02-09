import argparse
import datetime as dt
import json
import os
import time
from pathlib import Path, PurePath

import git
from py4j.java_gateway import GatewayParameters, JavaGateway

API_URL = os.getenv('NZSHM22_TOSHI_API_URL', "http://127.0.0.1:5000/graphql")
API_KEY = os.getenv('NZSHM22_TOSHI_API_KEY', "")
S3_URL = os.getenv('NZSHM22_TOSHI_S3_URL', "http://localhost:4569")


class BuilderTask:
    """
    The python client for a Diagpostics Report
    """

    def __init__(self, job_args):

        self.use_api = job_args.get('use_api', False)

        # setup the java gateway binding
        self._gateway = JavaGateway(gateway_parameters=GatewayParameters(port=job_args['java_gateway_port']))
        self._report_builder = self._gateway.entry_point.getInversionDiagnosticsReportBuilder()

        repos = ["opensha", "nshm-nz-opensha"]
        self._repoheads = get_repo_heads(PurePath(job_args['root_folder']), repos)
        self._output_folder = PurePath(job_args.get('working_path'))

        if self.use_api:
            # headers={"x-api-key":API_KEY}
            # self._ruptgen_api = RuptureGenerationTask(
            #     API_URL, S3_URL, None, with_schema_validation=True, headers=headers
            # )
            # # self._general_api = GeneralTask(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
            # self._task_relation_api = TaskRelation(API_URL, None, with_schema_validation=True, headers=headers)
            pass

    def run(self, task_arguments, job_arguments):

        # print(task_arguments)
        # print(job_arguments)

        t0 = dt.datetime.utcnow()

        # environment = {
        #     "host": platform.node(),
        #     "gitref_opensha": self._repoheads['opensha'],
        #     "gitref_nshm-nz-opensha": self._repoheads['nshm-nz-opensha'],
        # }

        if self.use_api:
            # create new task in toshi_api
            # task_id = self._ruptgen_api.create_task(
            #     dict(created=dt.datetime.now(tzutc()).isoformat()),
            #     arguments=task_arguments,
            #     environment=environment
            #     )

            # #link task tp the parent task
            # self._task_relation_api.create_task_relation(job_arguments['general_task_id'], task_id)

            # # #link task to the input datafile
            # input_file_id = task_arguments.get('rupture_set_file_id') or
            #   task_arguments.get('inversion_solution_file_id')
            # if input_file_id:
            #     self._ruptgen_api.link_task_file(task_id, input_file_id, 'READ')
            pass
        else:
            pass
            # task_id = None

        # Run the task....
        ta, ja = task_arguments, job_arguments

        # skippping other faults models for now
        fault_model_name = ta["short_name"].split("-")[0]  # "CFM_0_9_SANSTVZ_D90-0.0" remove thinning value
        if not (fault_model_name == "CFM_0_9_SANSTVZ_D90"):
            return

        # self._report_builder\
        #     .setRuptureSetName(ta['solution_file'])

        meta_folder = Path(self._output_folder, ta['rupture_set_file_id'])
        meta_folder.mkdir(parents=True, exist_ok=True)
        # dump the job metadata
        with open(Path(meta_folder, "metadata.json"), "w") as write_file:
            json.dump(dict(job_arguments=ja, task_arguments=ta), write_file, indent=4)

        # # build the MagRate Curve
        # mag_rates_folder = Path(self._output_folder, ta['rupture_set_file_id'], 'MagRates')
        # mag_rates_folder.mkdir(parents=True, exist_ok=True)

        # self._report_builder\
        #     .setName("")\
        #     .setOutputDir(str(mag_rates_folder))\
        #     .generateRateDiagnosticsPlot()

        # diags_folder = Path(self._output_folder, ta['rupture_set_file_id'], 'DiagnosticsReport')
        # diags_folder.mkdir(parents=True, exist_ok=True)

        # # build the full report
        # report_title = f"Solution-{ta['short_name']}-{ta['rupture_class']}-ce({ta['completion_energy']})
        # -{ta['max_inversion_time']}mins-rnd({ta['round_number']})"

        # self._report_builder\
        #     .setName(report_title)\
        #     .setOutputDir(str(diags_folder))\
        #     .generateInversionDiagnosticsReport()

        # build the Named Fault MFDS
        named_mfds_folder = Path(self._output_folder, ta['rupture_set_file_id'], 'named_fault_mfds')
        named_mfds_folder.mkdir(parents=True, exist_ok=True)

        plot_builder = self._gateway.entry_point.getMFDPlotBuilder()
        plot_builder.setOutputDir(str(named_mfds_folder)).setFaultModel(fault_model_name).setSolution(
            ta['solution_file']
        ).plot()

        t1 = dt.datetime.utcnow()
        print("Report took %s secs" % (t1 - t0).total_seconds())

        # capture task metrics
        # duration = (dt.datetime.utcnow() - t0).total_seconds()

        if self.use_api:
            # record the completed task
            # done_args = {
            #  'task_id':task_id,
            #  'duration':duration,
            #  'result':"SUCCESS",
            #  'state':"DONE",
            # }
            # self._ruptgen_api.complete_task(done_args, metrics)

            # upload the task output
            # self._ruptgen_api.upload_task_file(task_id, output_file, 'WRITE', meta=task_arguments)

            # #and the log files, why not
            # java_log_file = self._output_folder.joinpath(f"java_app.{job_arguments['java_gateway_port']}.log")
            # self._ruptgen_api.upload_task_file(task_id, java_log_file, 'WRITE')
            # pyth_log_file = self._output_folder.joinpath(f"python_script.{job_arguments['java_gateway_port']}.log")
            # self._ruptgen_api.upload_task_file(task_id, pyth_log_file, 'WRITE')
            pass

        else:
            # print(metrics)
            pass
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
    time.sleep(config['job_arguments']['task_id'] * 0.333 * 2 * 4)

    # print(config)
    task = BuilderTask(config['job_arguments'])
    task.run(**config)
