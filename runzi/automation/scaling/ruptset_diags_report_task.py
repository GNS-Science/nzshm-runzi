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
from runzi.util.aws.s3_folder_upload import upload_to_bucket
from runzi.automation.scaling.local_config import (WORK_PATH, API_KEY, API_URL, S3_URL, S3_REPORT_BUCKET)


class BuilderTask():
    """
    The python client for a Diagnostics Report
    """
    def __init__(self, job_args):

        self.use_api = job_args.get('use_api', False)

        #setup the java gateway binding
        self._gateway = JavaGateway(gateway_parameters=GatewayParameters(port=job_args['java_gateway_port']))
        #self._report_builder = self._gateway.entry_point.getInversionDiagnosticsReportBuilder()
        self._page_gen = self._gateway.entry_point.getReportPageGen()
        self._output_folder = PurePath(job_args.get('working_path'))

    def run(self, task_arguments, job_arguments):

        t0 = dt.datetime.utcnow()

        # Run the task....
        ta, ja = task_arguments, job_arguments

        meta_folder = Path(self._output_folder, ta['rupture_set_file_id'])
        meta_folder.mkdir(parents=True, exist_ok=True)

        #dump the job metadata
        with open(Path(meta_folder, "metadata.json"), "w") as write_file:
            json.dump(dict(job_arguments=ja, task_arguments=ta), write_file, indent=4)

        diags_folder = Path(self._output_folder, ta['rupture_set_file_id'], 'DiagnosticsReport')
        diags_folder.mkdir(parents=True, exist_ok=True)

        # # build the full report
        report_title = f"Rupture Set Diagnostics: {ta['rupture_set_file_id']}"

        self._page_gen\
            .setRuptureSet(ta['rupture_set_file_path'])\
            .setName(report_title)\
            .setOutputPath(str(diags_folder))\
            .setPlotLevel(ja['build_report_level'])\
            .setFillSurfaces(True)\
            .generateRupSetPage()

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
    upload_to_bucket(config['task_arguments']['rupture_set_file_id'], S3_REPORT_BUCKET)
