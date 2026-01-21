import argparse
import datetime as dt
import json
import time
import urllib
from pathlib import Path, PurePath

import git
from py4j.java_gateway import GatewayParameters, JavaGateway

from runzi.automation.scaling.file_utils import download_files, get_output_file_id
from runzi.automation.scaling.local_config import API_KEY, API_URL, S3_REPORT_BUCKET, S3_URL, WORK_PATH
from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.runners.runner_inputs import InversionReportArgs, SystemArgs
from runzi.util.aws.s3_folder_upload import upload_to_bucket

# from runzi.util.build_named_fault_mfd_index import build_named_fault_mfd_index


class BuilderTask:
    """
    The python client for a Diagnostics Report
    """

    def __init__(self, user_args: InversionReportArgs, system_args: SystemArgs):

        # setup the java gateway binding
        self.user_args = user_args
        self.system_args = system_args
        self.solution_id = self.user_args.solution_id

        self.gateway = JavaGateway(gateway_parameters=GatewayParameters(port=self.system_args.java_gateway_port))
        self.page_gen = self.gateway.entry_point.getReportPageGen()
        self.output_folder = PurePath(WORK_PATH)

    def run(self):

        # download the file
        headers = {"x-api-key": API_KEY}
        self.toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
        file_generator = get_output_file_id(self.toshi_api, self.solution_id)  # for file by file ID
        solutions = download_files(self.toshi_api, file_generator, str(WORK_PATH), overwrite=False)
        self.solution_info = solutions[self.solution_id]
        self.filepath = self.solution_info['filepath']

        meta_folder = Path(self.output_folder, self.solution_id)
        meta_folder.mkdir(parents=True, exist_ok=True)
        # dump the job metadata
        with open(Path(meta_folder, "metadata.json"), "w") as write_file:
            json.dump(
                dict(
                    user_args=self.user_args.model_dump(mode='json'),
                    system_args=self.system_args.model_dump(mode='json'),
                ),
                write_file,
                indent=4,
            )

        if self.user_args.build_mfd_plots:
            self.build_mfd_plots()

        if self.user_args.build_report_level:
            self.build_opensha_report()

    def build_opensha_report(self):
        t0 = dt.datetime.now()

        # build the MagRate Curve
        solution_report_folder = Path(self.output_folder, self.solution_id, 'solution_report')
        solution_report_folder.mkdir(parents=True, exist_ok=True)

        self.page_gen.setName(f"Solution Diagnostics: {self.solution_id}").setSolution(self.filepath).setOutputPath(
            str(solution_report_folder)
        ).setPlotLevel(self.user_args.build_report_level).setFillSurfaces(True).generatePage()

        t1 = dt.datetime.now()
        print("Report took %s secs" % (t1 - t0).total_seconds())

    def build_mfd_plots(self):
        t0 = dt.datetime.now()

        # # build the Named Fault MFDS, only if we have a FM with named faults
        # if ("CFM_0_9" in ta["fault_model"]) | ("CFM_1_0" in ta["fault_model"]):
        #     print("Named fault plots for: ", ta['file_id'], ta['fault_model'])
        #     print("path: ", ta['file_path'])

        fault_model = self.user_args.fault_model
        named_mfds_folder = Path(self.output_folder, self.solution_id, 'named_fault_mfds')
        named_mfds_folder.mkdir(parents=True, exist_ok=True)

        plot_builder = self.gateway.entry_point.getMFDPlotBuilder()
        # plot_builder.setCrustalSolution(self.filepath).setOutputDir(str(named_mfds_folder)).setFaultModel(fault_model)
        plot_builder.setCrustalSolution(self.filepath).setOutputDir(str(named_mfds_folder))
        plot_builder.plot()

        t1 = dt.datetime.now()
        print("MFD plots took %s secs" % (t1 - t0).total_seconds())


def get_repo_heads(rootdir, repos):
    result = {}
    for reponame in repos:
        repo = git.Repo(rootdir.joinpath(reponame))
        headcommit = repo.head.commit
        result[reponame] = headcommit.hexsha
    return result


if __name__ == "__main__":

    # TODO: this pattern is repeated for all tasks, use common function(s)
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
    user_args = InversionReportArgs(**config['task_args'])
    system_args = SystemArgs(**config['task_system_args'])
    task = BuilderTask(user_args, system_args)

    # maybe the JVM App is a little slow to get listening
    time.sleep(5)
    # Wait for some more time, scaled by taskid to avoid S3 consistency issue
    time.sleep(system_args.task_count)

    task.run()

    # TODO: build_named_fault_mfd_index() is broken
    # build_named_fault_mfd_index()

    upload_to_bucket(user_args.solution_id, S3_REPORT_BUCKET)
