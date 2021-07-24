import argparse
import json
import git
import os
import base64
from pathlib import PurePath, Path
import platform

from py4j.java_gateway import JavaGateway, GatewayParameters
import datetime as dt
from dateutil.tz import tzutc

import time

API_URL  = os.getenv('NZSHM22_TOSHI_API_URL', "http://127.0.0.1:5000/graphql")
API_KEY = os.getenv('NZSHM22_TOSHI_API_KEY', "")
S3_URL = os.getenv('NZSHM22_TOSHI_S3_URL',"http://localhost:4569")

class BuilderTask():
    """
    The python client for a Diagnostics Report
    """
    def __init__(self, job_args):

        self.use_api = job_args.get('use_api', False)

        #setup the java gateway binding
        self._gateway = JavaGateway(gateway_parameters=GatewayParameters(port=job_args['java_gateway_port']))
        self._report_builder = self._gateway.entry_point.getInversionDiagnosticsReportBuilder()
        self._output_folder = PurePath(job_args.get('working_path'))

    def run(self, task_arguments, job_arguments):

        t0 = dt.datetime.utcnow()

        # Run the task....
        ta, ja = task_arguments, job_arguments

        self._report_builder\
            .setRuptureSetName(ta['file_path'])

        meta_folder = Path(self._output_folder, ta['file_id'])
        meta_folder.mkdir(parents=True, exist_ok=True)
        #dump the job metadata
        with open(Path(meta_folder, "metadata.json"), "w") as write_file:
            json.dump(dict(job_arguments=ja, task_arguments=ta), write_file, indent=4)

        # build the MagRate Curve
        mag_rates_folder = Path(self._output_folder, ta['file_id'], 'mag_rates')
        mag_rates_folder.mkdir(parents=True, exist_ok=True)

        self._report_builder\
            .setName("")\
            .setOutputDir(str(mag_rates_folder))\
            .generateRateDiagnosticsPlot()

        # build the Named Fault MFDS, only if we have a FM with named faults
        if ta["fault_model"][:7] == "CFM_0_9":
            print("Named fault plots for: ", ta['file_id'])
            named_mfds_folder = Path(self._output_folder, ta['file_id'], 'named_fault_mfds')
            named_mfds_folder.mkdir(parents=True, exist_ok=True)

            plot_builder = self._gateway.entry_point.getMFDPlotBuilder()
            plot_builder \
                .setOutputDir(str(named_mfds_folder))\
                .setSolution(ta['file_path'])\
                .setFaultModel(ta['fault_model'])\
                .plot()

        t1 = dt.datetime.utcnow()
        print("Report took %s secs" % (t1-t0).total_seconds())


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
    f= open(config_file, 'r', encoding='utf-8')
    config = json.load(f)

    # maybe the JVM App is a little slow to get listening
    time.sleep(5)
    # Wait for some more time, scaled by taskid to avoid S3 consistency issue
    time.sleep(config['job_arguments']['task_id'] )

    # print(config)
    task = BuilderTask(config['job_arguments'])
    task.run(**config)
