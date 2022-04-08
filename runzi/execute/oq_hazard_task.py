#!python3 openquake_hazard_task.py
import argparse
import json

import os
import io
import zipfile
import subprocess
import requests
import platform
import logging

from pathlib import Path, PurePath
from importlib import import_module
import datetime as dt
from dateutil.tz import tzutc

from runzi.automation.scaling.toshi_api import ToshiApi, SubtaskType
from nshm_toshi_client.task_relation import TaskRelation
from runzi.automation.scaling.local_config import (API_KEY, API_URL, S3_URL, WORK_PATH, SPOOF_HAZARD)
from runzi.automation.scaling.file_utils import download_files, get_output_file_ids, get_output_file_id


logging.basicConfig(level=logging.INFO)

loglevel = logging.INFO
logging.getLogger('py4j.java_gateway').setLevel(loglevel)
logging.getLogger('nshm_toshi_client.toshi_client_base').setLevel(loglevel)
logging.getLogger('nshm_toshi_client.toshi_file').setLevel(loglevel)
logging.getLogger('urllib3').setLevel(loglevel)
logging.getLogger('botocore').setLevel(loglevel)
logging.getLogger('git.cmd').setLevel(loglevel)

log = logging.getLogger(__name__)

def build_sources_xml(sources_list):
    template = """
<nrml xmlns:gml="http://www.opengis.net/gml"
      xmlns="http://openquake.org/xmlns/nrml/0.5">
    <logicTree logicTreeID="Combined">
        <logicTreeBranchSet uncertaintyType="sourceModel" branchSetID="BS-NONCE1">
            <logicTreeBranch branchID="Combined">
                <uncertaintyModel>
<!-- INSERT_SOURCE_FILE_LIST -->
                </uncertaintyModel>
                <uncertaintyWeight>1.0</uncertaintyWeight>
            </logicTreeBranch>
        </logicTreeBranchSet>
    </logicTree>
</nrml>
"""
    insert = " " * 16 #coz some indentation is nice
    for filepath in sources_list:
        insert += f"{filepath}\n"

    template = template.replace('<!-- INSERT_SOURCE_FILE_LIST -->', insert)
    return template

def write_sources(xml_str, filepath):
    with open(filepath, 'w') as mf:
        mf.write(xml_str)

def archive(source_path, output_zip):
    '''
    zip contents of source path and return the full archive path.
    '''
    zip = zipfile.ZipFile(output_zip, 'w')

    for root, dirs, files in os.walk(source_path):
        for file in files:
            filename = str(PurePath(root, file))
            arcname = str(filename).replace(source_path, '')
            zip.write(filename, arcname )
    return output_zip


# def CDC_unpack_sources(ta, source_path):
#     namelist = []
#     for solution_id,file_name in zip(ta['solution_ids'],ta['file_names']):
#         print('=============')
#         print('solution_id:',solution_id)
#         print('file_name:',file_name)
#         print('=============')
#         with zipfile.ZipFile(Path(WORK_PATH, "downloads", solution_id, file_name), 'r') as zip_ref:
#             zip_ref.extractall(source_path)
#             namelist += zip_ref.namelist()
#     return namelist


def explode_config_template(config_info, working_path: str):
    config_folder = Path(working_path, "config")

    r1 = requests.get(config_info['file_url'])
    file_path = Path(working_path, config_info['file_name'])

    with open(file_path, 'wb') as f:
        f.write(r1.content)
        print("downloaded input file:", file_path, f)
        assert os.path.getsize(file_path) == config_info['file_size']

    with zipfile.ZipFile(file_path, 'r') as zip_ref:
        zip_ref.extractall(config_folder)
        return config_folder


def execute_openquake(configfile, logfile):

    oq_result = dict()

    if SPOOF_HAZARD:
        print("execute_openquake skipping SPOOF=True")
        oq_result['csv_archive']=Path(f"{configfile}.csv_archive.zip")
        oq_result['hdf5_archive']=Path(f"{configfile}.hdf5_archive.zip")
        oq_result['csv_archive'].touch()
        oq_result['hdf5_archive'].touch()
        return oq_result
    try:

        #oq engine --run /WORKING/examples/18_SWRG_INIT/4-sites_many-periods_vs30-475.ini -L /WORKING/examples/18_SWRG_INIT/jobs/BG_unscaled.log
        cmd = ['oq', 'engine', '--run', f'{configfile}', '-L',  f'{logfile}']

        print(f'cmd 1: {cmd}')

        subprocess.check_call(cmd)

        def get_last_task():
            """
            root@tryharder-ubuntu:/app# oq engine --lhc
            job_id |     status |          start_time |         description
                 6 |   complete | 2022-03-29 01:12:16 | 35 sites, few periods
            """

            cmd = ['oq', 'engine', '--lhc']
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
            out, err = p.communicate()

            fileish = io.StringIO()
            fileish.write(out.decode())
            fileish.seek(0)

            fileish.readline() #consume header
            #lines = fileish.readlines()
            for line in fileish.readlines():
                print(line)
                task = int(line.split("|")[0])

            return task

        last_task = get_last_task()
        output_path = Path(WORK_PATH, ta["work_folder"], "output", ta["solution_id"])

        #get the job ID

        """
        oq engine --export-outputs 12 /WORKING/examples/output/PROD/34-sites-few-CRU+BG
        cp /home/openquake/oqdata/calc_12.hdf5 /WORKING/examples/output/PROD
        """
        cmd = ['oq', 'engine', '--export-outputs', str(output_path)]
        print(f'cmd 2: {cmd}')
        subprocess.check_call(cmd)

        oq_result['csv_archive'] = archive(Path(output_path), Path(WORK_PATH, 'oq_csv_archive.zip'))

        #oq_result['csv_archive'] = "output_path"
        #cmd = ["cp", f"/home/openquake/oqdata/calc_{last_task}.hdf5", str(output_path)]
        #print(f'cmd 3: {cmd}')
        #subprocess.check_call(cmd)

        OQDATA = "/home/openquake/oqdata"
        hdf5_file = f"calc_{last_task}.hdf5"
        oq_result['hdf5_archive'] = archive(Path(OQDATA, hdf5_file), Path(WORK_PATH, 'oq_hdf5_archive.zip'))

        #Not need for API
        # write_meta(Path(work_folder, 'metadata.json'), task_arguments, job_arguments)

    except Exception as err:
        print(f"err: {err}")


    return oq_result

class BuilderTask():

    def __init__(self, job_args):

        self.use_api = job_args.get('use_api', False)
        self._output_folder = PurePath(job_args.get('working_path'))

        headers={"x-api-key":API_KEY}
        self._toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
        self._task_relation_api = TaskRelation(API_URL, None, with_schema_validation=True, headers=headers)

    def unpack_sources(self, ta, source_path):
        """download and extract the sources"""

        namelist = []
        for src_name, nrml_id in ta['sources']['nrml_ids'].items():

            log.info(f"get src : {src_name} {nrml_id}")

            gen = get_output_file_id(self._toshi_api, nrml_id)

            source_nrml = download_files(self._toshi_api, gen, str(WORK_PATH), overwrite=False)
            log.info(f"source_nrml: {source_nrml}")

            with zipfile.ZipFile(source_nrml[nrml_id]['filepath'], 'r') as zip_ref:
                zip_ref.extractall(source_path)
                namelist += zip_ref.namelist()
        return namelist


    def run(self, task_arguments, job_arguments):
        # Run the task....
        t0 = dt.datetime.utcnow()
        ta, ja = task_arguments, job_arguments

        environment = {
            "host": platform.node(),
            "openquake.version": "SPOOFED" if SPOOF_HAZARD else "TODO: get openquake version"
            }

        ## Create the OpenquakeHazardTask, with task details
        if self.use_api:

            #create the configuration from the template
            archive_id = ta['config_archive_id']
            config_id = self._toshi_api.openquake_hazard_config.create_config(
                [ta['nrml_id']],        # list [NRML source IDS],
                archive_id) # config_archive_template file

            #create the backref from the archive file to the configuration
            # NB the archive file is created by run_save_oq_configuration_template.pt
            self._toshi_api.openquake_hazard_config.create_archive_file_relation(
                config_id, archive_id, role = 'READ')

            #create new OpenquakeHazardTask, attaching the configuration (Revert standard AutomationTask)
            task_id = self._toshi_api.openquake_hazard_task.create_task(
                dict(
                    created = dt.datetime.now(tzutc()).isoformat(),
                    model_type = ta['model_type'].upper(),
                    config_id = config_id
                    ),
                arguments=task_arguments,
                environment=environment
                )

            #link OpenquakeHazardTask to the parent GT
            gt_conn = self._task_relation_api.create_task_relation(job_arguments['general_task_id'], task_id)
            print(f"created task_relationship: {gt_conn} for at: {task_id} on GT: {job_arguments['general_task_id']}")

        work_folder = ja['working_path']

        # TODO this doesn't work if we don't use the API!!
        # get the configuration_archive, we created above (maybe don't need the API for this step)
        #config_template_info = self._toshi_api.file.get_download_url(ta['config_archive_id'])
        config_template_info = self._toshi_api.get_file_detail(ta['config_archive_id'])

        print(config_template_info)

        #unpack the templates
        config_folder = explode_config_template(config_template_info, work_folder)

        # sources are the InversionSolutionNRML XML file(s) to include in the sources list
        sources_folder = Path(config_folder, 'sources')
        sources_list = self.unpack_sources(ta, sources_folder)
        print(f'sources_list: {sources_list}')

        # now the customised source_models.xml file must be written into the local configuration
        src_xml = build_sources_xml(sources_list)
        print(src_xml)
        write_sources(src_xml, Path(sources_folder, 'source_model.xml'))

        # Do the heavy lifting in openquake , passing the config
        for itm in config_template_info['meta']:
            if itm['k'] == "config_filename":
                config_filename = itm['v']
                break

        config_file = Path(config_folder, config_filename)
        logfile = Path(work_folder, f'openquake.log')

        oq_result = execute_openquake(config_file, logfile)

        if self.use_api:

            # save the two output archives
            csv_archive_id, post_url = self._toshi_api.file.create_file(oq_result['csv_archive'])
            self._toshi_api.file.upload_content(post_url, oq_result['csv_archive'])

            hdf5_archive_id, post_url = self._toshi_api.file.create_file(oq_result['hdf5_archive'])
            self._toshi_api.file.upload_content(post_url, oq_result['hdf5_archive'])

            # save the hazard solution
            solution_id = self._toshi_api.openquake_hazard_solution.create_solution(
                config_id, csv_archive_id, hdf5_archive_id, produced_by=task_id)

            # update the OpenquakeHazardTask
            self._toshi_api.openquake_hazard_task.complete_task(
                dict(task_id =task_id,
                    hazard_solution_id = solution_id,
                    duration = (dt.datetime.utcnow() - t0).total_seconds(),
                    result = "SUCCESS",
                    state = "DONE"))

        t1 = dt.datetime.utcnow()
        print("Task took %s secs" % (t1-t0).total_seconds())

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    args = parser.parse_args()

    try:
        # LOCAL and CLUSTER this is a file
        f = open(args.config, 'r', encoding='utf-8')
        config = json.load(f)
    except:
        # for AWS this must be a quoted JSON string
        config = json.loads(urllib.parse.unquote(args.config))

    task = BuilderTask(config['job_arguments'])
    task.run(**config)
