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

# Sizing measured with scripts/rupset_report_mem_bench.py: a cold, headless FULL report has a ~16 GB
# heap floor (OOMs at 12 GB, ~6.6 GB live set but heavy plot-image churn needs ~2.4x that). On AWS the
# heap is derived from the container memory as -Xmx = ecs_memory/1000 - 2, so ecs_memory is the lever
# that reaches Batch (jvm_heap_max is LOCAL/CLUSTER only). This job is memory-bound with trivial CPU
# need, so it runs on Fargate (default job definition) where vCPU and memory are billed separately:
# 4 vCPU / 30720 MB is the Fargate 4-vCPU max -> -Xmx 28 G (~75% over the floor), with no stranded
# instance vCPUs. Keep jvm_heap_max in step with the derived -Xmx so the two heaps don't disagree.
default_submission_args = SubmissionArgs(
    task_language=TaskLanguage.JAVA,
    java_threads=4,
    jvm_heap_max=28,
    ecs_max_job_time_min=200,
    ecs_memory=30720,
    ecs_vcpu=4,
)


class RupsetReportArgs(BaseModel):
    # This is a misnomer for convenience so that we can re-use some functions that assume this member is present.
    # It is actually a rupture set id.
    source_solution_id: str
    """The rupture set ID. It is named `source_solution_id` for programming conveninece, but is the rupture set."""

    build_report_level: str | None


class RupsetReportTask:
    """The python client for a Diagnostics Report."""

    def __init__(self, user_args: RupsetReportArgs, runtime_args: TaskRuntimeArgs):

        self.user_args = user_args
        self.runtime_args = runtime_args

        # setup the java gateway binding
        self.gateway = JavaGateway(gateway_parameters=GatewayParameters(port=runtime_args.java_gateway_port))
        self.page_gen = self.gateway.entry_point.getReportPageGen()
        self.output_folder = PurePath(WORK_PATH)

    def run(self):
        rupture_set_id = self.user_args.source_solution_id

        # download the file
        self.toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=False, **get_auth_kwargs())
        file_generator = get_output_file_id(self.toshi_api, rupture_set_id)  # for file by file ID
        solutions = download_files(self.toshi_api, file_generator, str(WORK_PATH), overwrite=False)
        rupture_set_info = solutions[rupture_set_id]
        rupture_set_filepath = rupture_set_info['filepath']

        meta_folder = Path(self.output_folder, rupture_set_id)
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

        diags_folder = Path(self.output_folder, rupture_set_id, 'DiagnosticsReport')
        diags_folder.mkdir(parents=True, exist_ok=True)

        # # build the full report
        report_title = f"Rupture Set Diagnostics: {rupture_set_id}"

        self.page_gen.setRuptureSet(rupture_set_filepath).setName(report_title)
        self.page_gen.setOutputPath(str(diags_folder))
        self.page_gen.setPlotLevel(self.user_args.build_report_level)
        self.page_gen.setFillSurfaces(True)

        if not SPOOF:
            self.page_gen.generateRupSetPage()
            if self.runtime_args.use_api:
                upload_to_bucket(self.user_args.source_solution_id, S3_REPORT_BUCKET, force_upload=True)


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
    user_args = RupsetReportArgs(**config['task_args'])
    runtime_args = TaskRuntimeArgs(**config['task_runtime_args'])
    task = RupsetReportTask(user_args, runtime_args)

    # Wait for some more time, scaled by taskid to avoid S3 consistency issue
    time.sleep(runtime_args.task_count)

    task.run()
