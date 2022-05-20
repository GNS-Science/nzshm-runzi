from pathlib import PurePath, Path
import argparse
import json
import urllib
import time
import datetime as dt

from nshm_toshi_client.task_relation import TaskRelation
from oq_hazard_report.report_builder import ReportBuilder

from runzi.util.aws.s3_folder_upload import upload_to_bucket

from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.automation.scaling.local_config import (WORK_PATH, API_KEY, API_URL, S3_URL, S3_REPORT_BUCKET)


class BuilderTask():

    """
    The python client for creating OpenQuake hazard reports
    """
    def __init__(self, job_args):

        self.use_api = job_args.get('use_api', False)
        self._output_folder = PurePath(WORK_PATH)

        if self.use_api:
            headers={"x-api-key":API_KEY}
            self._toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
            self._task_relation_api = TaskRelation(API_URL, None, with_schema_validation=True, headers=headers)

    def run(self, task_arguments, job_arguments):
        # Run the task....
        t0 = dt.datetime.utcnow()

        ta, ja = task_arguments, job_arguments

        hazard_report_folder = Path(self._output_folder, ta['hazard_id'], 'hazard_report')
        hazard_report_folder.mkdir(parents=True, exist_ok=True)
        print('hazard_report_folder',hazard_report_folder)

        report_name = f'Hazard Diagnostics: {ta["hazard_id"]}'
        
        report_builder = ReportBuilder()
        report_builder.setName(report_name)
        report_builder.setPlotTypes(['hcurve','uhs'])
        report_builder.setHazardArchive(ta['file_path'])
        report_builder.setOutputPath(str(hazard_report_folder))

        report_builder.run()

        t1 = dt.datetime.utcnow()
        print("Report took %s secs" % (t1-t0).total_seconds())


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

    # Wait for some more time, scaled by taskid to avoid S3 consistency issue
    time.sleep(config['job_arguments']['task_id'] )

    # print(config)
    task = BuilderTask(config['job_arguments'])
    task.run(**config)
    upload_to_bucket(config['task_arguments']['hazard_id'], S3_REPORT_BUCKET,root_path='openquake/DATA')
    