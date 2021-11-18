import argparse
import json
from runzi.automation.scaling.local_config import S3_REPORT_BUCKET
import git
import os
import base64
from pathlib import PurePath, Path
import platform
import urllib

from runzi.util.build_named_fault_mfd_index import build_named_fault_mfd_index
from py4j.java_gateway import JavaGateway, GatewayParameters
import datetime as dt
from dateutil.tz import tzutc
from runzi.util.aws import get_secret, upload_to_bucket

import time

API_URL  = os.getenv('NZSHM22_TOSHI_API_URL', "http://127.0.0.1:5000/graphql")
API_KEY = os.getenv('NZSHM22_TOSHI_API_KEY', "")
S3_URL = os.getenv('NZSHM22_TOSHI_S3_URL',"http://localhost:4569")

#Get API key from AWS secrets manager
if 'TEST' in API_URL.upper():
    API_KEY = get_secret("NZSHM22_TOSHI_API_SECRET_TEST", "us-east-1").get("NZSHM22_TOSHI_API_KEY_TEST")
elif 'PROD' in API_URL.upper():
    API_KEY = get_secret("NZSHM22_TOSHI_API_SECRET_PROD", "us-east-1").get("NZSHM22_TOSHI_API_KEY_PROD")

class BuilderTask():
    """
    The python client for a Diagnostics Report
    """
    def __init__(self, job_args):

        self.use_api = job_args.get('use_api', False)

        #setup the java gateway binding
        self._gateway = JavaGateway(gateway_parameters=GatewayParameters(port=job_args['java_gateway_port']))
        self._report_builder = self._gateway.entry_point.getInversionDiagnosticsReportBuilder()
        self._page_gen = self._gateway.entry_point.getReportPageGen()
        self._output_folder = PurePath(job_args.get('working_path'))

    def run(self, task_arguments, job_arguments):
        # Run the task....
        ta, ja = task_arguments, job_arguments

        meta_folder = Path(self._output_folder, ta['file_id'])
        meta_folder.mkdir(parents=True, exist_ok=True)
        #dump the job metadata
        with open(Path(meta_folder, "metadata.json"), "w") as write_file:
            json.dump(dict(job_arguments=ja, task_arguments=ta), write_file, indent=4)

        if ja.get('build_mfd_plots'):
            self.build_mfd_plots(task_arguments, job_arguments)

        if ja.get('build_report_level'):
            self.build_opensha_report(task_arguments, job_arguments)

    def build_opensha_report(self, task_arguments, job_arguments):
        t0 = dt.datetime.utcnow()
        ta, ja = task_arguments, job_arguments
        # build the MagRate Curve
        solution_report_folder = Path(self._output_folder, ta['file_id'], 'solution_report')
        solution_report_folder.mkdir(parents=True, exist_ok=True)

        self._page_gen\
            .setName(f"Solution Diagnostics: {ta['file_id']}")\
            .setSolution(ta['file_path'])\
            .setOutputPath(str(solution_report_folder))\
            .setPlotLevel(job_arguments['build_report_level'])\
            .setFillSurfaces(True)\
            .generatePage()

        t1 = dt.datetime.utcnow()
        print("Report took %s secs" % (t1-t0).total_seconds())

    def build_mfd_plots(self, task_arguments, job_arguments):
        t0 = dt.datetime.utcnow()
        ta, ja = task_arguments, job_arguments
        self._report_builder\
            .setRuptureSetName(ta['file_path'])

        # build the MagRate Curve
        mag_rates_folder = Path(self._output_folder, ta['file_id'], 'mag_rates')
        mag_rates_folder.mkdir(parents=True, exist_ok=True)

        self._report_builder\
            .setName("")\
            .setOutputDir(str(mag_rates_folder))\
            .generateRateDiagnosticsPlot()

        # build the Named Fault MFDS, only if we have a FM with named faults
        if ta["fault_model"][:7] == "CFM_0_9":
            print("Named fault plots for: ", ta['file_id'], ta['fault_model'])
            print("path: ", ta['file_path'])

            named_mfds_folder = Path(self._output_folder, ta['file_id'], 'named_fault_mfds')
            named_mfds_folder.mkdir(parents=True, exist_ok=True)

            plot_builder = self._gateway.entry_point.getMFDPlotBuilder()
            plot_builder\
                .setCrustalSolution(ta['file_path'])\
                .setOutputDir(str(named_mfds_folder))\
                .setFaultModel(ta['fault_model'])
            plot_builder.plot()

        t1 = dt.datetime.utcnow()
        print("MFD plots took %s secs" % (t1-t0).total_seconds())


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
        f= open(args.config, 'r', encoding='utf-8')
        config = json.load(f)
    except:
        # for AWS this must be a quoted JSON string
        config = json.loads(urllib.parse.unquote(args.config))

    # maybe the JVM App is a little slow to get listening
    time.sleep(5)
    # Wait for some more time, scaled by taskid to avoid S3 consistency issue
    time.sleep(config['job_arguments']['task_id'] )

    # print(config)
    task = BuilderTask(config['job_arguments'])
    task.run(**config)
    build_named_fault_mfd_index()
    upload_to_bucket(config['task_arguments']['file_id'], S3_REPORT_BUCKET)

