"""Openquake Hazard Task."""
#!python3 openquake_hazard_task.py

import argparse
import json
import os
import zipfile
import subprocess
import time
import platform
import logging
from pathlib import Path
import datetime as dt
import itertools
import copy

from dateutil.tz import tzutc
import requests


from nshm_toshi_client.task_relation import TaskRelation

from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.automation.scaling.local_config import (API_KEY, API_URL, S3_URL, WORK_PATH, SPOOF_HAZARD)

from runzi.util.aws import decompress_config
from runzi.execute.openquake.util import ( OpenquakeConfig, SourceModelLoader, build_sources_xml,
    get_logic_tree_file_ids, get_logic_tree_branches, single_permutation, build_disagg_sources_xml, build_gsim_xml)
from runzi.execute.openquake.execute_openquake import execute_openquake

logging.basicConfig(level=logging.DEBUG)

LOG_INFO = logging.INFO
logging.getLogger('py4j.java_gateway').setLevel(LOG_INFO)
logging.getLogger('nshm_toshi_client.toshi_client_base').setLevel(logging.DEBUG)
logging.getLogger('nshm_toshi_client.toshi_file').setLevel(LOG_INFO)
logging.getLogger('urllib3').setLevel(LOG_INFO)
logging.getLogger('botocore').setLevel(LOG_INFO)
logging.getLogger('git.cmd').setLevel(LOG_INFO)
logging.getLogger('gql.transport').setLevel(logging.WARN)

log = logging.getLogger(__name__)


def write_sources(xml_str, filepath):
    with open(filepath, 'w') as mf:
        mf.write(xml_str)


def get_config_filename(config_template_info):
    for itm in config_template_info['meta']:
        if itm['k'] == "config_filename":
            return itm['v']

def build_site_csv(location):

    backarc_locs = [
        '-36.870~174.770',
        '-39.590~174.280',
        '-37.780~175.280',
        '-35.220~173.970',
        '-39.070~174.080',
        '-38.230~175.870',
        '-37.130~175.530',
        '-37.690~176.170',
        '-38.680~176.080',
        '-38.140~176.250'
    ]

    lat,lon = location.split('~')
    site_csv = 'lon,lat,backarc\n'
    backarc_flag = 1 if location in backarc_locs else 0
    site_csv += f'{lon},{lat},{int(backarc_flag)}'    

    return site_csv


def explode_config_template(config_info, working_path: str, task_no: int):
    config_folder = Path(working_path, f"config_{task_no}")

    r1 = requests.get(config_info['file_url'])
    file_path = Path(working_path, config_info['file_name'])

    with open(file_path, 'wb') as f:
        f.write(r1.content)
        log.info(f"downloaded input file: {file_path}")
        f.close()

    assert os.path.getsize(file_path) == config_info['file_size']

    with zipfile.ZipFile(file_path, 'r') as zip_ref:
        zip_ref.extractall(config_folder)
        return config_folder

class BuilderTask():

    def __init__(self, job_args):

        self.use_api = job_args.get('use_api', False)

        headers={"x-api-key":API_KEY}
        self._toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
        self._task_relation_api = TaskRelation(API_URL, None, with_schema_validation=True, headers=headers)


    def _save_config(self, archive_id, logic_tree_id_list):
        #create the configuration from the template

        config_id = self._toshi_api.openquake_hazard_config.create_config(
            logic_tree_id_list,    # list [NRML source IDS],
            archive_id) # config_archive_template file

        #create the backref from the archive file to the configuration
        # NB the archive file is created by run_save_oq_configuration_template.pt
        self._toshi_api.openquake_hazard_config.create_archive_file_relation(
            config_id, archive_id, role = 'READ')

        return config_id

    def _setup_automation_task(self, task_arguments, job_arguments, config_id, logic_tree_id_list, environment):
        #create the configuration from the template

        #create new OpenquakeHazardTask, attaching the configuration (Revert standard AutomationTask)
        print('='*50)
        print('task arguments ...')
        print(task_arguments)
        print('='*50)
        automation_task_id = self._toshi_api.openquake_hazard_task.create_task(
            dict(
                created = dt.datetime.now(tzutc()).isoformat(),
                model_type = task_arguments['model_type'].upper(),
                config_id = config_id
                ),
            arguments=task_arguments,
            environment=environment
            )

        #link OpenquakeHazardTask to the parent GT
        gt_conn = self._task_relation_api.create_task_relation(job_arguments['general_task_id'], automation_task_id)
        print(f"created task_relationship: {gt_conn} for at: {automation_task_id} on GT: {job_arguments['general_task_id']}")

        return automation_task_id

    def _store_modified_config(self, config_folder, task_arguments, oq_result, config_id):
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

        return modconf_id

    def _store_api_result(self, automation_task_id, task_arguments, oq_result, config_id, modconf_id, duration):
        """Record results in API."""
        ta = task_arguments

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

        # # Predecessors...
        # log.info(f'logic_tree_id_list: {logic_tree_id_list[:5]} ...')
        # predecessors = list(map(lambda ssid: dict(id=ssid[1], depth=-1), logic_tree_id_list))
        # log.info(f'predecessors: {predecessors[:5]}')
        # source_predecessors = list(itertools.chain.from_iterable(map(lambda ssid: self._toshi_api.get_predecessors(ssid[1]), logic_tree_id_list)))

        # if source_predecessors:
        #     for predecessor in source_predecessors:
        #         predecessor['depth'] += -1
        #         predecessors.append(predecessor)
        predecessors = []

        # Save the hazard solution
        if not oq_result.get('no_result'):
            solution_id = self._toshi_api.openquake_hazard_solution.create_solution(
                config_id, csv_archive_id, hdf5_archive_id, produced_by=automation_task_id, predecessors=predecessors,
                modconf_id=modconf_id, task_args_id=task_args_id, meta=task_arguments)
            metrics = dict()
        else:
            solution_id = 'NO_RESULT'
            metrics = {'no_result': 'TRUE'}

        # update the OpenquakeHazardTask
        self._toshi_api.openquake_hazard_task.complete_task(
            dict(task_id =automation_task_id,
                hazard_solution_id = solution_id,
                duration = duration,
                result = "SUCCESS",
                state = "DONE"),
            metrics=metrics
        )
        
        return solution_id


    def run(self, task_arguments, job_arguments):
        """Run the job, routing to the correct job implementation."""
        ta, ja = task_arguments, job_arguments
        environment = {
            "host": platform.node(),
            "openquake.version": "SPOOFED" if SPOOF_HAZARD else "TODO: get openquake version"
        }

        if ta.get('logic_tree_permutations'):
            # This is LTB based oqenquake hazard job
            self.run_hazard(task_arguments, job_arguments, environment)
            return
        if ta.get('disagg_config'):
            self.run_disaggregation(task_arguments, job_arguments, environment)
            return
        raise ValueError("Invalid configuration.")



    def _sterilize_task_arguments(self, ta):
        ta_clean = copy.deepcopy(ta)
        for trt, gsim in ta_clean['disagg_config']['gsims'].items():
            ta_clean['disagg_config']['gsims'][trt] = gsim.replace('"','``').replace('\n','-')
        return ta_clean


    #   __| (_)___  __ _  __ _  __ _ _ __ ___  __ _  __ _| |_(_) ___  _ __
    #  / _` | / __|/ _` |/ _` |/ _` | '__/ _ \/ _` |/ _` | __| |/ _ \| '_ \
    # | (_| | \__ \ (_| | (_| | (_| | | |  __/ (_| | (_| | |_| | (_) | | | |
    #  \__,_|_|___/\__,_|\__, |\__, |_|  \___|\__, |\__,_|\__|_|\___/|_| |_|
    #                    |___/ |___/          |___/
    def run_disaggregation(self, task_arguments, job_arguments, environment):
        # Run the disagg ask....
        t0 = dt.datetime.utcnow()
        ta, ja = task_arguments, job_arguments

        #############
        # DISAGG sources are in the config
        #############
        disagg_config = ta['disagg_config']
        ta['vs30'] = disagg_config['vs30']
        inv_id, bg_id = disagg_config['source_ids']
        ta['logic_tree_permutations'] = [{'permute':[{'members':[{'tag': 'DISAGG', 'inv_id': inv_id, 'bg_id': bg_id, 'weight': 1.0}]}]}] 

        # get the InversionSolutionNRML XML file(s) to include in the sources list
        nrml_id_list = list(filter(lambda _id: len(_id), ta['disagg_config']['source_ids']))

        log.info(f"sources: {nrml_id_list}")

        ############
        # API SETUP
        ############
        automation_task_id = None
        if self.use_api:
            ta_clean = self._sterilize_task_arguments(ta) if ta['disagg_config'].get('gsims') else ta                
            archive_id = ta['hazard_config']
            config_id = self._save_config(archive_id, nrml_id_list)
            automation_task_id = self._setup_automation_task(ta_clean, ja, config_id, nrml_id_list, environment)

        #########################
        # Baseline CONFIG
        #########################
        work_folder = WORK_PATH
        config_template_info = self._toshi_api.get_file_detail(ta['hazard_config'])
        config_filename = "job.ini" #  get_config_filename(config_template_info) TODO not set int meta?

        #unpack the templates
        config_folder = explode_config_template(config_template_info, work_folder, ja['task_id'])
        sources_folder = Path(config_folder, 'sources')
        source_file_mapping = SourceModelLoader().unpack_sources_in_list(nrml_id_list, sources_folder)

        flattened_files = []
        for key, val in source_file_mapping.items():
            flattened_files += val['sources']

        ##################
        # SOURCE XML
        ##################
        source_xml = build_disagg_sources_xml(flattened_files)
        src_xml_file = Path(sources_folder, 'source_model.xml')
        write_sources(source_xml, src_xml_file)
        log.info(f'wrote xml sources file: {src_xml_file}')

        ##################
        # GSIMS XML
        ##################
        # gsim_xml = build_gsim_xml(disagg_config['gsims'])
        # gsim_xml_file = Path(config_folder, 'gsim_model.xml')
        # write_sources(gsim_xml, gsim_xml_file)
        # log.info(f'wrote xml gsim  file: {gsim_xml_file}')


        ##################
        # SITE
        ##################
        site_csv = build_site_csv(disagg_config['location'])
        site_csv_file = Path(config_folder, 'site.csv')
        write_sources(site_csv, site_csv_file)
        log.info(f'wrote csv site file: {site_csv_file}')


        ###############
        # CONFIGURE JOB
        ###############
        disagg_settings = disagg_config.get('disagg_settings')
        lat, lon = disagg_config["location"].split("~")
        config_file = Path(config_folder, config_filename)
        def modify_config(config_file, task_arguments):
            "modify_config for openquake hazard task."""
            ta = task_arguments
            config = OpenquakeConfig(open(config_file))\
                .set_description(f"Disaggregation for site: {disagg_config.get('site_name')}, vs30: {disagg_config['vs30']}, IMT: {disagg_config['imt']}, level: {round(disagg_config['level'], 12)}")\
                .set_disaggregation(enable = True, values=disagg_settings)\
                .set_iml_disagg(imt=disagg_config['imt'], level=round(disagg_config['level'], 12))\
                .clear_iml()\
                .set_rupture_mesh_spacing("5")\
                .set_ps_grid_spacing("30")\
                .set_vs30(disagg_config['vs30'])\
                .set_rlz_index(disagg_config['nrlz'])\
                .set_disagg_site_model()
                # .set_gsim_logic_tree_file("./gsim_model.xml")\
                # .set_disagg_site(lat, lon)
            config.write(open(config_file, 'w'))

        modify_config(config_file, task_arguments)

        ##############
        # EXECUTE
        ##############
        oq_result = execute_openquake(config_file, ja['task_id'], automation_task_id)


        ######################
        # API STORE RESULTS #
        ######################
        if self.use_api:
            #TODO store modified config
            ta_clean = self._sterilize_task_arguments(ta) if ta['disagg_config'].get('gsims') else ta
            solution_id = self._store_api_result(automation_task_id, ta_clean, oq_result, config_id,
                modconf_id=config_id, #  TODO use modified config id
                duration = (dt.datetime.utcnow() - t0).total_seconds())


            #############################
            # STORE HAZARD REALIZATIONS #
            #############################
            # run the store_hazard job
            if not SPOOF_HAZARD and not oq_result.get('no_result'):
                # [{'tag': 'GRANULAR', 'weight': 1.0, 'permute': [{'group': 'ALL', 'members': [ltb._asdict()] }]}]
                # TODO GRANULAR ONLY@!@
                # ltb = {"tag": "hiktlck, b0.979, C3.9, s0.78", "weight": 0.0666666666666667, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwODA3NQ==", "bg_id":"RmlsZToxMDY1MjU="},

                """
                positional arguments:
                  calc_id              an openquake calc id OR filepath to the hdf5 file.
                  toshi_hazard_id      hazard_solution id.
                  toshi_gt_id          general_task id.
                  locations_id         identifier for the locations used (common-py ENUM ??)
                  source_tags          e.g. "hiktlck, b0.979, C3.9, s0.78"
                  source_ids           e.g. "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwODA3NQ==,RmlsZToxMDY1MjU="

                optional arguments:
                  -h, --help           show this help message and exit
                  -c, --create-tables  Ensure tables exist.
                """
                # ltb = ta['logic_tree_permutations'][0]['permute'][0]['members'][0]
                inv_id, bg_id = disagg_config['source_ids']
                tag = 'DISAGG'
                cmd = ['store_hazard_v3',
                        str(oq_result['oq_calc_id']),
                        solution_id,
                        job_arguments['general_task_id'],
                        f'"{disagg_config["location"]}"',
                        f'"{tag}"',
                        f'"{inv_id}, {bg_id}"',
                        '--verbose',
                        '--meta-data-only',
                        '--create-tables']
                log.info(f'store_hazard: {cmd}')
                subprocess.check_call(cmd)

        t1 = dt.datetime.utcnow()
        log.info("Task took %s secs" % (t1-t0).total_seconds())


    # | |__   __ _ ______ _ _ __ __| |
    # | '_ \ / _` |_  / _` | '__/ _` |
    # | | | | (_| |/ / (_| | | | (_| |
    # |_| |_|\__,_/___\__,_|_|  \__,_|
    #
    def run_hazard(self, task_arguments, job_arguments, environment):
        # Run the hazard task....
        t0 = dt.datetime.utcnow()
        ta, ja = task_arguments, job_arguments

        #############
        # HAZARD sources and ltbs
        #############
        logic_tree_permutations = ta['logic_tree_permutations']
        if ta.get('split_source_branches'):
            print(f'logic_tree_permutations: {logic_tree_permutations}')
            log.info(f"splitting sources for task_id {ta['split_source_id']}")
            logic_tree_permutations = [single_permutation(logic_tree_permutations, ta['split_source_id'])]
            log.info(f"new logic_tree_permutations: {logic_tree_permutations}")

        # sources are the InversionSolutionNRML XML file(s) to include in the sources list
        logic_tree_id_list = get_logic_tree_file_ids(logic_tree_permutations)

        log.info(f"sources: {logic_tree_id_list}")


        ############
        # API SETUP
        ############
        automation_task_id = None
        if self.use_api:
            id_list = [_id[1] for _id in logic_tree_id_list]
            archive_id = ta['config_archive_id']
            config_id = self._save_config(archive_id, id_list)
            automation_task_id = self._setup_automation_task(ta, ja, config_id, [id[1] for id in logic_tree_id_list], environment)

        #########################
        # SETUP openquake CONFIG
        #########################

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

        config_filename = get_config_filename(config_template_info)

        ###############
        # HAZARD CONFIG
        ###############
        config_file = Path(config_folder, config_filename)
        def modify_config(config_file, task_arguments):
            "modify_config for openquake hazard task."""
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

        ##############
        # EXECUTE
        ##############
        oq_result = execute_openquake(config_file, ja['task_id'], automation_task_id)

        ######################
        # API STORE RESULTS #
        ######################
        if self.use_api:
            solution_id = self._store_api_result(automation_task_id, task_arguments, oq_result, config_id,
                modconf_id=config_id, #  TODO use modified config id
                duration = (dt.datetime.utcnow() - t0).total_seconds())

            #############################
            # STORE HAZARD REALIZATIONS #
            #############################
            # run the store_hazard job
            if not SPOOF_HAZARD:
                # [{'tag': 'GRANULAR', 'weight': 1.0, 'permute': [{'group': 'ALL', 'members': [ltb._asdict()] }]}]
                # TODO GRANULAR ONLY@!@
                # ltb = {"tag": "hiktlck, b0.979, C3.9, s0.78", "weight": 0.0666666666666667, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwODA3NQ==", "bg_id":"RmlsZToxMDY1MjU="},

                """
                positional arguments:
                  calc_id              an openquake calc id OR filepath to the hdf5 file.
                  toshi_hazard_id      hazard_solution id.
                  toshi_gt_id          general_task id.
                  locations_id         identifier for the locations used (common-py ENUM ??)
                  source_tags          e.g. "hiktlck, b0.979, C3.9, s0.78"
                  source_ids           e.g. "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwODA3NQ==,RmlsZToxMDY1MjU="

                optional arguments:
                  -h, --help           show this help message and exit
                  -c, --create-tables  Ensure tables exist.
                """
                ltb = ta['logic_tree_permutations'][0]['permute'][0]['members'][0]
                cmd = ['store_hazard_v3',
                        str(oq_result['oq_calc_id']),
                        solution_id,
                        job_arguments['general_task_id'],
                        ta['location_code'],
                        f'"{ltb["tag"]}"',
                        f'"{ltb["inv_id"]}, {ltb["bg_id"]}"',
                        '--verbose',
                        '--create-tables']
                log.info(f'store_hazard: {cmd}')
                subprocess.check_call(cmd)

        t1 = dt.datetime.utcnow()
        log.info("Task took %s secs" % (t1-t0).total_seconds())


# _ __ ___   __ _(_)_ __
#  | '_ ` _ \ / _` | | '_ \
#  | | | | | | (_| | | | | |
#  |_| |_| |_|\__,_|_|_| |_|
#
if __name__ == "__main__":
    """Fancy ascii text comes from https://patorjk.com/software/taag/#p=display&v=0&f=Standard&t=main."""
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

    time.sleep(int(config['job_arguments']['task_id']) * 2 )
    task = BuilderTask(config['job_arguments'])
    task.run(**config)
