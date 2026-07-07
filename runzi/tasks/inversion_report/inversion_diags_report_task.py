import datetime as dt
import json
import time
from pathlib import Path, PurePath

import git
from py4j.java_gateway import GatewayParameters, JavaGateway
from pydantic import BaseModel

from runzi.arguments import SubmissionArgs, TaskLanguage, TaskRuntimeArgs
from runzi.automation.file_utils import download_files, get_output_file_id
from runzi.automation.local_config import API_URL, S3_REPORT_BUCKET, S3_URL, SPOOF, WORK_PATH, get_auth_kwargs
from runzi.automation.toshi_api import ToshiApi
from runzi.aws.s3_folder_upload import upload_to_bucket
from runzi.tasks.get_config import get_config

default_submission_args = SubmissionArgs(
    task_language=TaskLanguage.JAVA,
    java_threads=16,
    jvm_heap_max=32,
    ecs_max_job_time_min=60,
    ecs_memory=30720,
    ecs_vcpu=4,
)


class InversionReportArgs(BaseModel):
    """Inversion report arguments."""

    source_solution_id: str
    build_mfd_plots: bool
    build_report_level: str | None
    hack_fault_model: str | None


class InversionReportTask:
    """
    The python client for a Diagnostics Report
    """

    def __init__(self, user_args: InversionReportArgs, runtime_args: TaskRuntimeArgs):

        # setup the java gateway binding
        self.user_args = user_args
        self.runtime_args = runtime_args
        self.solution_id = self.user_args.source_solution_id

        self.gateway = JavaGateway(gateway_parameters=GatewayParameters(port=self.runtime_args.java_gateway_port))
        self.page_gen = self.gateway.entry_point.getReportPageGen()
        self.output_folder = PurePath(WORK_PATH)

    def run(self):

        # download the file
        self.toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=False, **get_auth_kwargs())
        file_generator = get_output_file_id(self.toshi_api, self.solution_id)  # for file by file ID
        solutions = download_files(self.toshi_api, file_generator, str(WORK_PATH), overwrite=False)
        self.solution_info = solutions[self.solution_id]
        self.filepath = self.solution_info['filepath']

        # annoying that we have to get a new generator since we used it to download files already
        file_generator = get_output_file_id(self.toshi_api, self.solution_id)  # for file by file ID
        self.fault_model = next(file_generator).get('fault_model')

        meta_folder = Path(self.output_folder, self.solution_id)
        meta_folder.mkdir(parents=True, exist_ok=True)
        # dump the job metadata
        with open(Path(meta_folder, "metadata.json"), "w") as write_file:
            json.dump(
                dict(
                    user_args=self.user_args.model_dump(mode='json'),
                    runtime_args=self.runtime_args.model_dump(mode='json'),
                ),
                write_file,
                indent=4,
            )

        if not SPOOF:
            if self.user_args.build_mfd_plots:
                self.build_mfd_plots()

            if self.user_args.build_report_level:
                self.build_opensha_report()

            if self.runtime_args.use_api:
                upload_to_bucket(user_args.source_solution_id, S3_REPORT_BUCKET)

    def build_opensha_report(self):
        t0 = dt.datetime.now()

        # build the MagRate Curve
        solution_report_folder = Path(self.output_folder, self.solution_id, 'solution_report')
        solution_report_folder.mkdir(parents=True, exist_ok=True)

        self.page_gen.setName(f"Solution Diagnostics: {self.solution_id}").setSolution(self.filepath).setOutputPath(
            str(solution_report_folder)
        ).setPlotLevel(self.user_args.build_report_level).setFillSurfaces(True).generatePage()

        t1 = dt.datetime.now()
        print(f'Report took {(t1 - t0).total_seconds()} secs')

    def build_mfd_plots(self):
        t0 = dt.datetime.now()

        # # build the Named Fault MFDS, only if we have a FM with named faults
        # if ("CFM_0_9" in ta["fault_model"]) | ("CFM_1_0" in ta["fault_model"]):
        #     print("Named fault plots for: ", ta['file_id'], ta['fault_model'])
        #     print("path: ", ta['file_path'])

        fault_model = self.user_args.hack_fault_model
        if self.user_args.hack_fault_model:
            fault_model = self.user_args.hack_fault_model
        elif fault_model is None or fault_model == 'None':
            fault_model = "CUSTOM"

        named_mfds_folder = Path(self.output_folder, self.solution_id, 'named_fault_mfds')
        named_mfds_folder.mkdir(parents=True, exist_ok=True)

        plot_builder = self.gateway.entry_point.getMFDPlotBuilder()
        # TODO: Not sure why this is commented out
        # plot_builder.setCrustalSolution(self.filepath).setOutputDir(str(named_mfds_folder)).setFaultModel(fault_model)
        plot_builder.setCrustalSolution(self.filepath).setOutputDir(str(named_mfds_folder))
        plot_builder.plot()

        t1 = dt.datetime.now()
        print(f'MFD plots took {(t1 - t0).total_seconds()} secs')


def get_repo_heads(rootdir, repos):
    result = {}
    for reponame in repos:
        repo = git.Repo(rootdir.joinpath(reponame))
        headcommit = repo.head.commit
        result[reponame] = headcommit.hexsha
    return result


if __name__ == "__main__":
    config = get_config()

    # print(config)
    user_args = InversionReportArgs(**config['task_args'])
    runtime_args = TaskRuntimeArgs(**config['task_runtime_args'])
    task = InversionReportTask(user_args, runtime_args)

    # Wait for some more time, scaled by taskid to avoid S3 consistency issue
    time.sleep(runtime_args.task_count)

    task.run()

    # TODO: build_named_fault_mfd_index() is broken, I don't think it's used anymore
    # build_named_fault_mfd_index()
