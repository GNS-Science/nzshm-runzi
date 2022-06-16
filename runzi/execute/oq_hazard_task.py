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
import shutil

from pathlib import Path

import datetime as dt
from dateutil.tz import tzutc

import itertools

from runzi.automation.scaling.toshi_api import ToshiApi, SubtaskType
from nshm_toshi_client.task_relation import TaskRelation
from runzi.automation.scaling.local_config import (API_KEY, API_URL, S3_URL, WORK_PATH, SPOOF_HAZARD)

from runzi.util import archive
from runzi.util.aws import decompress_config
from runzi.execute.util import ( OpenquakeConfig, SourceModelLoader, build_sources_xml,
    get_logic_tree_file_ids, get_logic_tree_branches, single_permutation )

logging.basicConfig(level=logging.INFO)

loglevel = logging.INFO
logging.getLogger('py4j.java_gateway').setLevel(loglevel)
logging.getLogger('nshm_toshi_client.toshi_client_base').setLevel(loglevel)
logging.getLogger('nshm_toshi_client.toshi_file').setLevel(loglevel)
logging.getLogger('urllib3').setLevel(loglevel)
logging.getLogger('botocore').setLevel(loglevel)
logging.getLogger('git.cmd').setLevel(loglevel)
logging.getLogger('gql.transport').setLevel(logging.WARN)

log = logging.getLogger(__name__)

def write_sources(xml_str, filepath):
    with open(filepath, 'w') as mf:
        mf.write(xml_str)

def explode_config_template(config_info, working_path: str, task_no: int):
    config_folder = Path(working_path, f"config_{task_no}")

    r1 = requests.get(config_info['file_url'])
    file_path = Path(working_path, config_info['file_name'])

    with open(file_path, 'wb') as f:
        f.write(r1.content)
        print("downloaded input file:", file_path, f)
        assert os.path.getsize(file_path) == config_info['file_size']

    with zipfile.ZipFile(file_path, 'r') as zip_ref:
        zip_ref.extractall(config_folder)
        return config_folder

def execute_openquake(configfile, task_no, toshi_task_id):

    toshi_task_id = toshi_task_id or "DUMMY_toshi_TASK_ID"
    output_path = Path(WORK_PATH, f"output_{task_no}")
    logfile = Path(output_path, f'openquake.{task_no}.log')

    if output_path.exists():
        shutil.rmtree(output_path)
    output_path.mkdir()

    oq_result = dict()

    if SPOOF_HAZARD:
        print("execute_openquake skipping SPOOF=True")
        oq_result['csv_archive']=Path(WORK_PATH, f"spoof-{task_no}.csv_archive.zip")
        oq_result['hdf5_archive']=Path(WORK_PATH, f"spoof-{task_no}.hdf5_archive.zip")
        oq_result['csv_archive'].touch()
        oq_result['hdf5_archive'].touch()
        return oq_result

    try:

        #oq engine --run /WORKING/examples/18_SWRG_INIT/4-sites_many-periods_vs30-475.ini -L /WORKING/examples/18_SWRG_INIT/jobs/BG_unscaled.log
        cmd = ['oq', 'engine', '--run', f'{configfile}', '-L',  f'{logfile}']
        log.info(f'cmd 1: {cmd}')
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

        #get the job ID
        last_task = get_last_task()
        oq_result['oq_calc_id'] = last_task


        """
        oq engine --export-outputs 12 /WORKING/examples/output/PROD/34-sites-few-CRU+BG
        cp /home/openquake/oqdata/calc_12.hdf5 /WORKING/examples/output/PROD
        """
        cmd = ['oq', 'engine', '--export-outputs', str(last_task), str(output_path)]
        log.info(f'cmd 2: {cmd}')
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL)
        oq_result['csv_archive'] = archive(output_path, Path(WORK_PATH, f'openquake_csv_archive-{toshi_task_id}.zip'))

        #clean up export outputs
        shutil.rmtree(output_path)

        OQDATA = "/home/openquake/oqdata"
        hdf5_file = f"calc_{last_task}.hdf5"
        oq_result['hdf5_archive'] = archive(Path(OQDATA, hdf5_file), Path(WORK_PATH, f'openquake_hdf5_archive-{toshi_task_id}.zip'))

    except Exception as err:
        log.error(f"err: {err}")

    log.info(f"oq_result {oq_result}")
    return oq_result

class BuilderTask():

    def __init__(self, job_args):

        self.use_api = job_args.get('use_api', False)

        headers={"x-api-key":API_KEY}
        self._toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
        self._task_relation_api = TaskRelation(API_URL, None, with_schema_validation=True, headers=headers)

    def run(self, task_arguments, job_arguments):
        # Run the task....
        t0 = dt.datetime.utcnow()
        ta, ja = task_arguments, job_arguments

        environment = {
            "host": platform.node(),
            "openquake.version": "SPOOFED" if SPOOF_HAZARD else "TODO: get openquake version"
            }

        # now we have split this hazard job up, in whihc case the current job should run just the subset ....
        logic_tree_permutations = ta['logic_tree_permutations']
        if ta.get('split_source_branches'):
            print(f'logic_tree_permutations: {logic_tree_permutations}')
            log.info(f"splitting sources for task_id {ta['split_source_id']}")
            logic_tree_permutations = [single_permutation(logic_tree_permutations, ta['split_source_id'])]
            log.info(f"new logic_tree_permutations: {logic_tree_permutations}")

        # sources are the InversionSolutionNRML XML file(s) to include in the sources list
        id_list = get_logic_tree_file_ids(logic_tree_permutations)

        log.info(f"sources: {id_list}")
        ## Create the OpenquakeHazardTask, with task details

        task_id = None
        if self.use_api:

            #create the configuration from the template
            archive_id = ta['config_archive_id']
            config_id = self._toshi_api.openquake_hazard_config.create_config(
                [id[1] for id in id_list],    # list [NRML source IDS],
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

        work_folder = WORK_PATH

        # TODO this doesn't work if we don't use the API!!
        # get the configuration_archive, we created above (maybe don't need the API for this step)
        #config_template_info = self._toshi_api.file.get_download_url(ta['config_archive_id'])
        config_template_info = self._toshi_api.get_file_detail(ta['config_archive_id'])

        print(config_template_info)

        #unpack the templates
        config_folder = explode_config_template(config_template_info, work_folder, ja['task_id'])

        sources_folder = Path(config_folder, 'sources')

        source_file_mapping = SourceModelLoader().unpack_sources(logic_tree_permutations, sources_folder)
        #print(f'sources_list: {sources_list}')

        # now the customised source_models.xml file must be written into the local configuration
        ltbs = [ltb for ltb in get_logic_tree_branches(logic_tree_permutations)]
        print("LTB:", len(ltbs), ltbs[0])
        src_xml = build_sources_xml(ltbs, source_file_mapping)
        src_xml_file = Path(sources_folder, 'source_model.xml')
        write_sources(src_xml, src_xml_file)

        #prepare the config
        for itm in config_template_info['meta']:
            if itm['k'] == "config_filename":
                config_filename = itm['v']
                break

        config_file = Path(config_folder, config_filename)
        def modify_config(config_file, task_arguments):
            ta = task_arguments
            config = OpenquakeConfig(open(config_file))\
                .set_sites(ta['location_code'])\
                .set_disaggregation(enable = ta['disagg_conf']['enabled'],
                    values = ta['disagg_conf']['config'])\
                .set_iml(ta['intensity_spec']['measures'],
                    ta['intensity_spec']['levels'])\
                .set_vs30(ta['vs30'])\
                .set_rupture_mesh_spacing(ta['rupture_mesh_spacing'])\
                .set_ps_grid_spacing(ta['ps_grid_spacing'])
            config.write(open(config_file, 'w'))

        modify_config(config_file, task_arguments)

        oq_result = execute_openquake(config_file, ja['task_id'], task_id)

        if self.use_api:

            # TODO: bundle up the sources and modified config for possible re-runs
            log.info("create modified_configs")
            modconf_zip = Path(config_folder, 'modified_config.zip')
            with zipfile.ZipFile(modconf_zip, 'w') as zfile:
                for filename in [config_file, src_xml_file]:
                    arcname = str(filename.relative_to(config_folder))
                    zfile.write(filename,  arcname )

            # save the modified config archives
            modconf_id, post_url = self._toshi_api.file.create_file(modconf_zip)
            self._toshi_api.file.upload_content(post_url, modconf_zip)

            # make a json file from the ta dict so we can save it.
            task_args_json = Path(WORK_PATH, 'task_args.json')
            with open(task_args_json, 'w') as task_js:
                task_js.write(json.dumps(ta, indent=2))

            # save the json
            task_args_id, post_url = self._toshi_api.file.create_file(task_args_json)
            self._toshi_api.file.upload_content(post_url, task_args_json)

            # save the two output archives
            csv_archive_id, post_url = self._toshi_api.file.create_file(oq_result['csv_archive'])
            self._toshi_api.file.upload_content(post_url, oq_result['csv_archive'])

            hdf5_archive_id, post_url = self._toshi_api.file.create_file(oq_result['hdf5_archive'])
            self._toshi_api.file.upload_content(post_url, oq_result['hdf5_archive'])

            # Predecessors...
            log.info(f'id_list: {id_list[:5]} ...')
            predecessors = list(map(lambda ssid: dict(id=ssid[1], depth=-1), id_list))
            log.info(f'predecessors: {predecessors[:5]}')
            source_predecessors = list(itertools.chain.from_iterable(map(lambda ssid: self._toshi_api.get_predecessors(ssid[1]), id_list)))

            if source_predecessors:
                for predecessor in source_predecessors:
                    predecessor['depth'] += -1
                    predecessors.append(predecessor)

            # Save the hazard solution
            solution_id = self._toshi_api.openquake_hazard_solution.create_solution(
                config_id, csv_archive_id, hdf5_archive_id, produced_by=task_id, predecessors=predecessors,
                modconf_id=modconf_id, task_args_id=task_args_id)

            # update the OpenquakeHazardTask
            self._toshi_api.openquake_hazard_task.complete_task(
                dict(task_id =task_id,
                    hazard_solution_id = solution_id,
                    duration = (dt.datetime.utcnow() - t0).total_seconds(),
                    result = "SUCCESS",
                    state = "DONE"))

            # run the store_hazard job
            if not SPOOF_HAZARD:
                # options --new-version-only --create-tables --skip-rlzs --verbose
                cmd = ['store_hazard', str(oq_result['oq_calc_id']), solution_id, '--verbose', '--new-version-only']
                log.info(f'store_hazard: {cmd}')
                subprocess.check_call(cmd)

        t1 = dt.datetime.utcnow()
        log.info("Task took %s secs" % (t1-t0).total_seconds())

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    args = parser.parse_args()

    try:
        # LOCAL and CLUSTER this is a file
        f = open(args.config, 'r', encoding='utf-8')
        config = json.load(f)
    except:
        # for AWS this must now be a compressed JSON string
        config = json.loads(decompress_config(args.config))

    task = BuilderTask(config['job_arguments'])
    task.run(**config)
