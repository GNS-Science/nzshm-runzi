import argparse
import json
import time
import urllib
from pathlib import Path, PurePath

import git
from py4j.java_gateway import GatewayParameters, JavaGateway
from pydantic import BaseModel

from runzi.arguments import SystemArgs, TaskLanguage
from runzi.automation.scaling.file_utils import download_files, get_output_file_id
from runzi.automation.scaling.local_config import API_KEY, API_URL, S3_REPORT_BUCKET, S3_URL, SPOOF, USE_API, WORK_PATH
from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.aws.s3_folder_upload import upload_to_bucket

default_system_args = SystemArgs(
    task_language=TaskLanguage.JAVA,
    use_api=USE_API,
    java_threads=16,
    jvm_heap_max=32,
    ecs_max_job_time_min=60,
    ecs_memory=30720,
    ecs_vcpu=4,
    ecs_job_definition="Fargate-runzi-opensha-JD",
    ecs_job_queue="BasicFargate_Q",
)


class RupsetReportArgs(BaseModel):
    # This is a misnomer for convenience so that we can re-use some functions that assume this member is present.
    # It is actually a rupture set id.
    source_solution_id: str
    build_report_level: str | None


class RupsetReportTask:
    """The python client for a Diagnostics Report."""

    def __init__(self, user_args: RupsetReportArgs, system_args: SystemArgs):

        self.user_args = user_args
        self.system_args = system_args

        # setup the java gateway binding
        self.gateway = JavaGateway(gateway_parameters=GatewayParameters(port=system_args.java_gateway_port))
        self.page_gen = self.gateway.entry_point.getReportPageGen()
        self.output_folder = PurePath(WORK_PATH)

    def run(self):
        rupture_set_id = self.user_args.source_solution_id

        # download the file
        headers = {"x-api-key": API_KEY}
        self.toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
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
                    system_args=self.system_args.model_dump(mode='json'),
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
            if self.system_args.use_api:
                upload_to_bucket(user_args.source_solution_id, S3_REPORT_BUCKET, force_upload=True)


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
    user_args = RupsetReportArgs(**config['task_args'])
    system_args = SystemArgs(**config['task_system_args'])
    task = RupsetReportTask(user_args, system_args)

    # maybe the JVM App is a little slow to get listening
    time.sleep(5)
    # Wait for some more time, scaled by taskid to avoid S3 consistency issue
    time.sleep(system_args.task_count)

    task.run()
