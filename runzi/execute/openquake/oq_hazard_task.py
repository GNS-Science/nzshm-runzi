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

import dacite
from dateutil.tz import tzutc
import requests

from nshm_toshi_client.task_relation import TaskRelation
from nzshm_model.source_logic_tree import SourceLogicTree 
from nzshm_model.psha_adapter.openquake import OpenquakeSimplePshaAdapter
# from nzshm_model.source_logic_tree import SourceLogicTree # , FlattenedSourceLogicTree
# from nzshm_model.nrml.logic_tree import NrmlDocument

from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.automation.scaling.toshi_api.openquake_hazard.openquake_hazard_task import HazardTaskType
from runzi.automation.scaling.local_config import (API_KEY, API_URL, S3_URL, WORK_PATH, SPOOF_HAZARD)

from runzi.util.aws import decompress_config
# from runzi.execute.openquake.util import ( OpenquakeConfig, # SourceModelLoader, #  build_sources_xml,
#     #get_logic_tree_file_ids, get_logic_tree_branches, single_permutation, build_disagg_sources_xml, 
#     build_gsim_xml,
# )
from runzi.execute.openquake.util import OpenquakeConfig, build_site_csv, get_coded_locations, build_gsim_xml
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

REQUIRED_TASK_ARGS = [
    "intensity_spec",
    "location_list",
    "disagg_conf",
    "site_params",
    "srm_logic_tree",
]

def write_sources(xml_str, filepath):
    with open(filepath, 'w') as mf:
        mf.write(xml_str)


def get_config_filename(config_template_info):
    for itm in config_template_info['meta']:
        if itm['k'] == "config_filename":
            return itm['v']

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

    def _setup_automation_task(self, task_arguments, job_arguments, config_id, environment, task_type):
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
            environment=environment,
            task_type=task_type,
            )

        #link OpenquakeHazardTask to the parent GT
        gt_conn = self._task_relation_api.create_task_relation(job_arguments['general_task_id'], automation_task_id)
        print(f"created task_relationship: {gt_conn} for at: {automation_task_id} on GT: {job_arguments['general_task_id']}")

        return automation_task_id


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
        if not oq_result.get('no_ruptures'):
            csv_archive_id, post_url = self._toshi_api.file.create_file(oq_result['csv_archive'])
            self._toshi_api.file.upload_content(post_url, oq_result['csv_archive'])

            hdf5_archive_id, post_url = self._toshi_api.file.create_file(oq_result['hdf5_archive'])
            self._toshi_api.file.upload_content(post_url, oq_result['hdf5_archive'])

        predecessors = []

        # Save the hazard solution
        if oq_result.get('no_ruptures'):
            solution_id = None
            metrics = {'no_result': 'TRUE'}
        else:
            solution_id = self._toshi_api.openquake_hazard_solution.create_solution(
                config_id, csv_archive_id, hdf5_archive_id, produced_by=automation_task_id, predecessors=predecessors,
                modconf_id=modconf_id, task_args_id=task_args_id, meta=task_arguments)
            metrics = dict()

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

        if HazardTaskType[ta["task_type"]] is HazardTaskType.HAZARD:
            self.run_hazard(task_arguments, job_arguments, environment)
            return
        elif HazardTaskType[ta["task_type"]] is HazardTaskType.DISAGG:
            self.run_disaggregation(task_arguments, job_arguments, environment)
            return
        else:
            raise ValueError("Invalid configuration.")

    def _sterilize_task_arguments_gsims(self, ta):
        ta_clean = copy.deepcopy(ta)
        for trt, gsim in ta_clean['disagg_config']['gsims'].items():
            ta_clean['disagg_config']['gsims'][trt] = gsim.replace('"','``').replace('\n', '-')
        return ta_clean

    def _sterilize_task_arguments_gmcmlt(self, ta):
        ta_clean = copy.deepcopy(ta)
        ta_clean['gmcm_logic_tree'] = ta_clean['gmcm_logic_tree'].replace('"', '``').replace('\n', '-')
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
        # disagg_config = ta['disagg_config']
        # ta['vs30'] = disagg_config['vs30']
        # inv_id, bg_id = disagg_config['source_ids']
        # ta['logic_tree_permutations'] = [{'permute':[{'members':[{'tag': 'DISAGG', 'inv_id': inv_id, 'bg_id': bg_id, 'weight': 1.0}]}]}] 

        # get the InversionSolutionNRML XML file(s) to include in the sources list
        # filter out empty strings (e.g. when ther isn't an inversion source)
        # nrml_id_list = list(filter(lambda _id: len(_id), ta['disagg_config']['source_ids']))

        # log.info(f"sources: {nrml_id_list}")

        ############
        # API SETUP
        ############
        automation_task_id = None
        if self.use_api:
            task_type = HazardTaskType.DISAGG
            config_id = "T3BlbnF1YWtlSGF6YXJkQ29uZmlnOjEyOTI0NA==" # old config id until we've removed need for config_id when creating task
            ta_clean = self._sterilize_task_arguments_gmcmlt(ta)
            automation_task_id = self._setup_automation_task(ta_clean, ja, config_id, environment, task_type)

            # ta_clean = self._sterilize_task_arguments_gsims(ta) if ta['disagg_config'].get('gsims') else ta
            # archive_id = ta['hazard_config']
            # config_id = self._save_config(archive_id, nrml_id_list)
            # automation_task_id = self._setup_automation_task(ta_clean, ja, config_id, nrml_id_list, environment, task_type)

        #########################
        # Baseline CONFIG
        #########################
        # work_folder = WORK_PATH
        # config_template_info = self._toshi_api.get_file_detail(ta['hazard_config'])
        # config_filename = "job.ini" #  get_config_filename(config_template_info) TODO not set int meta?

        #unpack the templates
        # config_folder = explode_config_template(config_template_info, work_folder, ja['task_id'])
        # sources_folder = Path(config_folder, 'sources')
        # source_file_mapping = SourceModelLoader().unpack_sources_in_list(nrml_id_list, sources_folder)

        # flattened_files = []
        # for key, val in source_file_mapping.items():
        #     flattened_files += val['sources']

        #################################
        # SETUP openquake CONFIG FOLDER
        #################################
        work_folder = WORK_PATH
        task_no = ja["task_id"]
        config_folder = Path(work_folder, f"config_{task_no}")
        config_filename = "job.ini"

        ###########################
        # HAZARD sources and ltbs
        ###########################
        # using new version2 SourceLogicTree from nzshm_model>=0.5.0
        srm_logic_tree = SourceLogicTree.from_dict(ta['srm_logic_tree'])
        print(srm_logic_tree)
        sources_folder = Path(config_folder, 'sources')
        cache_folder = Path(config_folder, 'downloads')
        cache_folder.mkdir(parents=True, exist_ok=True)
        sources_folder.mkdir(parents=True, exist_ok=True)
        adapter = srm_logic_tree.psha_adapter(provider=OpenquakeSimplePshaAdapter)
        sources_filepath = adapter.write_config(cache_folder, sources_folder)
        sources_filepath = sources_filepath.relative_to(config_folder)
        for f in cache_folder.glob("*"):
            f.unlink()
        cache_folder.rmdir()

        ##################
        # SOURCE XML
        ##################
        # source_xml = build_disagg_sources_xml(flattened_files)
        # src_xml_file = Path(sources_folder, 'source_model.xml')
        # write_sources(source_xml, src_xml_file)
        # log.info(f'wrote xml sources file: {src_xml_file}')

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
        site_csv = build_site_csv([ta['location']])
        site_csv_file = Path(config_folder, 'site.csv')
        write_sources(site_csv, site_csv_file)
        log.info(f'wrote csv site file: {site_csv_file}')
        
        ##################
        # GMCM LOGIC TREE
        ##################
        gsim_xml = build_gsim_xml(ta["gmcm_logic_tree"])
        gsim_xml_file = Path(config_folder, 'gsim_model.xml')
        write_sources(gsim_xml, gsim_xml_file)


        ###############
        # CONFIGURE JOB
        ###############
        # disagg_settings = disagg_config.get('disagg_settings')
        # lat, lon = disagg_config["location"].split("~")
        # config_file = Path(config_folder, config_filename)
        # def modify_config(config_file, task_arguments):
        #     "modify_config for openquake hazard task."""
        #     ta = task_arguments
        #     config = OpenquakeConfig(open(config_file))\
        #         .set_description(f"Disaggregation for site: {disagg_config.get('site_name')}, vs30: {disagg_config['vs30']}, IMT: {disagg_config['imt']}, level: {round(disagg_config['level'], 12)}")\
        #         .set_disaggregation(enable = True, values=disagg_settings)\
        #         .clear_iml()\
        #         .set_rupture_mesh_spacing(ta["rupture_mesh_spacing"])\
        #         .set_ps_grid_spacing(ta["ps_grid_spacing"])\
        #         .set_vs30(disagg_config['vs30'])\
        #         .set_disagg_site_model()
        #         # .set_rlz_index(disagg_config['nrlz'])\
        #         # .set_gsim_logic_tree_file("./gsim_model.xml")\
        #         # .set_disagg_site(lat, lon)
        #     config.write(open(config_file, 'w'))

        # modify_config(config_file, task_arguments)

        ###############
        # OQ CONFIG
        ###############
        description = (f"Disaggregation for site: {ta['location']}, vs30: {ta['vs30']}, "
                       f"IMT: {ta['imt']}, level: {round(ta['level'], 12)}")
        config_filepath = Path(config_folder, config_filename)
        oq_config = OpenquakeConfig()\
            .set_description(description)\
            .set_sites("./sites.csv")\
            .set_source_logic_tree_file(str(sources_filepath))\
            .set_gsim_logic_tree_file("./gsim_model.xml")\
            .set_vs30(ta['vs30'])\
            .set_iml_disagg(imt=ta['imt'], level=ta['level'])
        task_arguments['oq']['general'].pop('description')
        for table, params in task_arguments['oq'].items():
            for name, value in params.items():
                oq_config.set_parameter(table, name, value)
        with config_filepath.open("w") as config_file:
            oq_config.write(config_file)


        ##############
        # EXECUTE
        ##############
        assert 0
        oq_result = execute_openquake(config_file, ja['task_id'], automation_task_id)

        ######################
        # API STORE RESULTS #
        ######################
        if self.use_api:
            
            #TODO store modified config
            ta_clean = self._sterilize_task_arguments_gsims(ta) if ta['disagg_config'].get('gsims') else ta
            solution_id = self._store_api_result(automation_task_id, ta_clean, oq_result, config_id,
                modconf_id=config_id, #  TODO use modified config id
                duration = (dt.datetime.utcnow() - t0).total_seconds())

            #############################
            # STORE HAZARD REALIZATIONS #
            #############################
            # run the store_hazard job
            if (not SPOOF_HAZARD) and (not oq_result.get('no_ruptures')):
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

        ################
        # API SETUP
        ################
        automation_task_id = None
        if self.use_api:
            task_type = HazardTaskType.HAZARD
            config_id = "T3BlbnF1YWtlSGF6YXJkQ29uZmlnOjEyOTI0NA==" # old config id until we've removed need for config_id when creating task
            ta_clean = self._sterilize_task_arguments_gmcmlt(ta)
            automation_task_id = self._setup_automation_task(ta_clean, ja, config_id, environment, task_type)

        #################################
        # SETUP openquake CONFIG FOLDER
        #################################
        work_folder = WORK_PATH
        task_no = ja["task_id"]
        config_folder = Path(work_folder, f"config_{task_no}")
        config_filename = "job.ini"

        ###########################
        # HAZARD sources and ltbs
        ###########################
        if ta.get('srm_logic_tree'):
            # using new version2 SourceLogicTree from nzshm_model>=0.5.0
            srm_logic_tree = SourceLogicTree.from_dict(ta['srm_logic_tree'])
            print(srm_logic_tree)
        # elif ta.get('srm_flat_logic_tree'):
        #     srm_logic_tree = dacite.from_dict(
        #         data_class=FlattenedSourceLogicTree, data=ta['srm_flat_logic_tree']
        #     )
        else:
            raise ValueError("task_arguments must have 'srm_logic_tree' or 'srm_flat_logic_tree' key")

        sources_folder = Path(config_folder, 'sources')
        cache_folder = Path(config_folder, 'downloads')
        cache_folder.mkdir(parents=True, exist_ok=True)
        sources_folder.mkdir(parents=True, exist_ok=True)
        adapter = srm_logic_tree.psha_adapter(provider=OpenquakeSimplePshaAdapter)
        sources_filepath = adapter.write_config(cache_folder, sources_folder)
        sources_filepath = sources_filepath.relative_to(config_folder)
        for f in cache_folder.glob("*"):
            f.unlink()
        cache_folder.rmdir()


        ##################
        # SITES
        ##################
        locations, vs30s = get_coded_locations(ta['location_list'])
        if ta['vs30'] == 0:
            site_csv = build_site_csv(locations, vs30s)
        else:
            site_csv = build_site_csv(locations)
        site_csv_file = Path(config_folder, 'sites.csv')
        write_sources(site_csv, site_csv_file)
        log.info(f'wrote csv site file: {site_csv_file}')

        ##################
        # GMCM LOGIC TREE
        ##################
        gsim_xml = build_gsim_xml(ta["gmcm_logic_tree"])
        gsim_xml_file = Path(config_folder, 'gsim_model.xml')
        write_sources(gsim_xml, gsim_xml_file)

        ###############
        # OQ CONFIG
        ###############
        config_filepath = Path(config_folder, config_filename)
        oq_config = OpenquakeConfig()\
            .set_sites("./sites.csv")\
            .set_source_logic_tree_file(str(sources_filepath))\
            .set_gsim_logic_tree_file("./gsim_model.xml")\
            .set_iml(ta['intensity_spec']['measures'],
                ta['intensity_spec']['levels'])\
            .set_vs30(ta['vs30'])
        for table, params in task_arguments['oq'].items():
            for name, value in params.items():
                oq_config.set_parameter(table, name, value)
        with config_filepath.open("w") as config_file:
            oq_config.write(config_file)

        ##############
        # EXECUTE
        ##############
        oq_result = execute_openquake(config_filepath, ja['task_id'], automation_task_id)

        ######################
        # API STORE RESULTS #
        ######################
        if self.use_api:
            
            solution_id = self._store_api_result(automation_task_id, ta_clean, oq_result, config_id,
                modconf_id=config_id, #  TODO use modified config id
                duration = (dt.datetime.utcnow() - t0).total_seconds())

            #############################
            # STORE HAZARD REALIZATIONS #
            #############################
            # run the store_hazard job
            if not SPOOF_HAZARD and (not oq_result.get('no_ruptures')):
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
                ltb = ta['srm_logic_tree']['fault_system_lts'][0]['branches']
                tag = ":".join((
                    srm_logic_tree.fault_system_lts[0].short_name,
                    str(srm_logic_tree.fault_system_lts[0].branches[0].values)
                ))
                inv_id = srm_logic_tree.fault_system_lts[0].branches[0].onfault_nrml_id
                bg_id = srm_logic_tree.fault_system_lts[0].branches[0].distributed_nrml_id
                cmd = ['store_hazard_v3',
                        str(oq_result['oq_calc_id']),
                        solution_id,
                        job_arguments['general_task_id'],
                        str(ta['location_list']),
                        f'"{tag}"',
                        f'"{inv_id}, {bg_id}"',
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
