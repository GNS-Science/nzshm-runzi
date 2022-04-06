#!python3 openquake_hazard_task.py
import argparse
import json


import os
import io
import zipfile
import subprocess

from pathlib import Path, PurePath
from importlib import import_module
import datetime as dt
from dateutil.tz import tzutc

from runzi.automation.scaling.toshi_api import ToshiApi, SubtaskType
from runzi.automation.scaling.local_config import (API_KEY, API_URL, S3_URL, WORK_PATH, SPOOF_HAZARD)

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
    insert = " " * 16 #indentation is nice
    for filepath in sources_list:
        insert += f"{filepath}\n"

    template = template.replace('<!-- INSERT_SOURCE_FILE_LIST -->', insert)
    return template

def write_sources(xml_str, filepath):
    with open(filepath, 'w') as mf:
        mf.write(xml_str)

def write_meta(filepath, task_arguments, job_arguments):
    meta = dict(
        solution_id = task_arguments["solution_id"],
        general_task_id = job_arguments['general_task_id'],
        meta =  dict(task_arguments=task_arguments, job_arguments=job_arguments))

    with open(filepath, 'a') as mf:
        mf.write( json.dumps(meta, indent=4) )
        mf.write( ",\n")

def unpack_sources(ta, source_path):
    with zipfile.ZipFile(Path(WORK_PATH, "downloads", ta['solution_id'], ta["file_name"]), 'r') as zip_ref:
        zip_ref.extractall(source_path)
        return zip_ref.namelist()

def explode_config_template(toshi_api:ToshiApi, working_path: str, config_template_id: str):
    config_folder = Path(working_path, "config")

    filedeets = toshi_api.file.get_download_url(config_template_id)

    r1 = requests.get(filedeets['file_url'])
    file_path = Path(working_path, filedeets['file_name'])

    with open(file_path, 'wb') as f:
        f.write(r1.content)
        print("downloaded input file:", file_path, f)
        assert os.path.getsize(file_path) == filedeets['file_size']

    with zipfile.ZipFile(file_path, 'r') as zip_ref:
        zip_ref.extractall(config_folder)
        return config_folder


def execute_openquake(configfile, logfile):
    if SPOOF_HAZARD:
        print("execute_openquake skipping SPOOF=True")
        return

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

        cmd = ["cp", f"/home/openquake/oqdata/calc_{last_task}.hdf5", str(output_path)]
        print(f'cmd 3: {cmd}')

        subprocess.check_call(cmd)

        #Not need for API
        write_meta(Path(work_folder, 'metadata.json'), task_arguments, job_arguments)

    except Exception as err:
        print(f"err: {err}")


class BuilderTask():

    def __init__(self, job_args):

        self.use_api = job_args.get('use_api', False)
        self._output_folder = PurePath(job_args.get('working_path'))

        headers={"x-api-key":API_KEY}
        self._toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
        self._task_relation_api = TaskRelation(API_URL, None, with_schema_validation=True, headers=headers)

    def run(self, task_arguments, job_arguments):
        # Run the task....
        t0 = dt.datetime.utcnow()
        ta, ja = task_arguments, job_arguments

        ## Create the OpenquakeHazardTask, with task details
        if self.use_api:
            # task_id = self._toshi_api.automation_task.create_task(
            #     dict(
            #         created=dt.datetime.now(tzutc()).isoformat(),
            #         task_type=SubtaskType.OPENQUAKE_HAZARD.value,
            #         model_type=ta['config_type'].upper(),
            #         ),
            #     arguments=task_arguments,
            #     environment=environment
            #     )
            pass

        work_folder = ja['working_path']

        # get the configuration_archive
        # see run_build_openquake_config_template.py
        config_folder = explode_config_template(
            self._toshi_api,
            work_folder,
            ta.get('config_template_id', 'RmlsZToxOA=='),)

        sources_folder = Path(config_folder, 'sources')

        # the download of sources to have occurred already prepare_inputs
        # sources are the Openquake Source NRML XML file(s) to include in the sources list
        sources_list = unpack_sources(ta, sources_folder)
        print(f'sources_list: {sources_list}')

        # the local source_models.xml file must be written to the configuration
        src_xml = build_sources_xml(sources_list)
        print(src_xml)
        write_sources(src_xml, Path(config_folder, 'source_model.xml'))

        ## now the complete config is written and ready to use, lets zip it and save it in the API.
        ## TODO
        ##
        ## link the OpenquakeHazardTask, with the config

        # Do the heavy lifting in openquake , passing the config
        configfile = Path(config_folder, ta["config_file"])
        logfile = Path(work_folder, f'{ta["solution_id"]}.log')

        execute_openquake(configfile, logfile)

        ## TODO
        ## Upload the hazard outputs
        ## link the hazard outputs to the OpenquakeHazardTask
        ## Mark the OpenquakeHazardTask as Done
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


    #TESTING

    # nrml_id = str(nrml_info['id']),
    # file_name = nrml_info['info']['file_name'],
    # config_file = config_file,
    # work_folder = subtask_arguments['work_folder'],
    # upstream_general_task=source_gt_id

    config = {
        "task_arguments": {
            "nrml_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwMDM0Mg==",
            "file_name": "NZSHM22_ScaledInversionSolution-QXV0b21hdGlvblRhc2s6MTAwMTIx_nrml.zip",
            "config_file": "many-sites_3-periods_vs30-475.ini",
            "upstream_general_task": "R2VuZXJhbFRhc2s6MTAwMjA2"
        },
        "job_arguments": {
            "task_id": 12,
            "working_path": "/app/tmp",
            "general_task_id": null,
            "use_api": true
        }
    }

    task = BuilderTask(config['job_arguments'])
    task.run(**config)
