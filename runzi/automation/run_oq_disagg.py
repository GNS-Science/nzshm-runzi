#!python3
"""
This script produces disagg tasks in either AWS, PBS or LOCAL that run OpenquakeHazard in disagg mode.

"""
import argparse
import logging
import csv
import json
import pwd
import os
import itertools
from collections import namedtuple
import datetime as dt

from pathlib import Path

from runzi.automation.scaling.toshi_api import ToshiApi, CreateGeneralTaskArgs, SubtaskType, ModelType
from runzi.configuration.oq_disagg import build_hazard_tasks, get_disagg_configs
from runzi.automation.scaling.schedule_tasks import schedule_tasks

from runzi.automation.scaling.local_config import (WORK_PATH, USE_API, JAVA_THREADS,
    API_KEY, API_URL, CLUSTER_MODE, EnvMode )

from runzi.CONFIG.OQ.SLT_v8 import logic_tree_permutations as logic_trees

# If you wish to override something in the main config, do so here ..
WORKER_POOL_SIZE = 1
# USE_API = False
DISAGG_TARGET_DIR = '/home/chrisdc/NSHM/Disaggs/Disagg_Targets'

Disagg = namedtuple("Disagg", "location imt vs30 poe")

def launch_gt(gt_config):

    t0 = dt.datetime.utcnow()

    logging.basicConfig(level=logging.INFO)

    loglevel = logging.INFO
    # logging.getLogger('nshm_toshi_client.toshi_client_base').setLevel(loglevel)
    # logging.getLogger('nshm_toshi_client.toshi_file').setLevel(loglevel)
    # logging.getLogger('urllib3').setLevel(loglevel)
    # logging.getLogger('botocore').setLevel(loglevel)
    logging.getLogger('gql.transport').setLevel(logging.WARN)
    log = logging.getLogger(__name__)

    new_gt_id = None

    # If using API give this task a descriptive setting...

    TASK_TITLE = "Openquake Disagg calcs"
    TASK_DESCRIPTION = "Full logic tree for SLT workshop"
    #TASK_DESCRIPTION = "TEST build"

    # disagg_settings = dict(mag_bin_width = 0.499)
    # disagg_settings = dict(mag_bin_width = 0.5)
    disagg_settings = dict(
        distance_bin_width = "0 5.0 10.0 15.0 20.0 30.0 40.0 50.0 60.0 80.0 100.0 140.0 180.0 220.0 260.0 320.0 380.0 500.0",
        num_epsilon_bins = 16,
        mag_bin_width = .1999,
        coordinate_bin_width = 5,
    )

    disagg_configs = get_disagg_configs(gt_config, logic_trees)
    for disagg_config in disagg_configs:
        disagg_config['disagg_settings'] = disagg_settings

    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)

    # TODO obtain the config (job.ini from the first nearest_rlz)
    # hazard_config = "RmlsZToxMDEyODA="  # toshi_id contain job config used by the original hazard jobs TEST for OQH : T3BlbnF1YWtlSGF6YXJkU29sdXRpb246MTAxMzE5
    # hazard_config = "RmlsZToxMTI2MTI="  # toshi_id contain job config used by the original hazard jobs PROD for OQH : T3BlbnF1YWtlSGF6YXJkU29sdXRpb246MTA2OTc3
    # hazard_config = "RmlsZToxMTQ3ODQ==" # PROD for T3BlbnF1YWtlSGF6YXJkU29sdXRpb246MTA4MTU3
    # hazard_config = "RmlsZToxMjEwMzQ=" # GSIM LT final v0b
    # hazard_config = "RmlsZToxMjg4MDY=" # GSIM LT final EE backarc
    # hazard_config = "RmlsZToxMzEwOTU=" # GSIM LT v2
    # hazard_config = "RmlsZToxMzQzNzU=" # GSIM LT v2 pointsource_distance = 50
    # hazard_config = "RmlsZToxMzY0MDY=" # GSIM LT v2 0.1deg+34
    hazard_config = "RmlsZTozNDYzODc=" # GSIM LT v2 0.1deg+34 renew 2

    args = dict(
        hazard_config = hazard_config,
        disagg_configs =  disagg_configs,
    )

    args_list = []
    for key, value in args.items():
        args_list.append(dict(k=key, v=value))

    task_type = SubtaskType.OPENQUAKE_HAZARD #TODO: create a new task type
    model_type = ModelType.COMPOSITE

    if USE_API:

        #create new task in toshi_api
        gt_args = CreateGeneralTaskArgs(
            agent_name=pwd.getpwuid(os.getuid()).pw_name,
            title=TASK_TITLE,
            description=TASK_DESCRIPTION
            )\
            .set_argument_list(args_list)\
            .set_subtask_type(task_type)\
            .set_model_type(model_type)

        new_gt_id = toshi_api.general_task.create_task(gt_args)

    print("GENERAL_TASK_ID:", new_gt_id)

    #tasks = build_tasks(new_gt_id, task_type, model_type, hazard_config, disagg_configs)

    tasks = list(build_hazard_tasks(new_gt_id, task_type, model_type, hazard_config, disagg_configs))
    if USE_API:
        toshi_api.general_task.update_subtask_count(new_gt_id, len(tasks))

    print(tasks)
    print('worker count: ', WORKER_POOL_SIZE)
    print(f'tasks to schedule: {len(tasks)}')

    schedule_tasks(tasks, WORKER_POOL_SIZE)

    print("GENERAL_TASK_ID:", new_gt_id)
    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())

    return new_gt_id


def generate_gt_configs(task_args, locations, poes, vs30s, imts):

    for (loc, poe, vs30, imt) in itertools.product(locations, poes, vs30s, imts):
        yield dict(
            location = loc,
            poe = poe,
            vs30 = vs30,
            imt = imt,
            inv_time = task_args['inv_time'],
            agg = task_args['agg'],
            hazard_model_id = task_args['hazard_model_id'],
        ), Disagg(loc, imt, vs30, poe)


def generate_single_gt_config(task_args, config):

    loc = config['location']
    poe = config['poe']
    vs30 = config['vs30']
    imt = config['imt']

    return dict(
        location = loc,
        poe = poe,
        vs30 = vs30,
        imt = imt,
        inv_time = task_args['inv_time'],
        agg = task_args['agg'],
        hazard_model_id = task_args['hazard_model_id'],
    ) 

def run_main(task_args, locations, imts, vs30s, poes, gt_filename, rerun=False):

    gt_filepath = Path(gt_filename)

    if gt_filepath.exists():
        raise Exception('file %s already exists, cannot overwrite' % gt_filepath)

    with open(gt_filepath, 'w') as df:
        disagg_writer = csv.writer(df)
        disagg_writer.writerow(['GT_ID', 'date', 'time', 'time_zone'] + list(Disagg._fields))
        if rerun:
            DISAGG_LIST = os.environ['NZSHM22_DISAGG_LIST']
            with open(DISAGG_LIST, 'r') as gt_list_file:
                reader = csv.reader(gt_list_file)
                gt_datas = []
                GTData = namedtuple("GTData", next(reader)[:-1], rename=True)
                for row in reader:
                    gt_datas.append(GTData(*row))
            

            with open(DISAGG_LIST, 'r') as gt_list_file:
                reader = csv.reader(gt_list_file)
                GTData = namedtuple("GTData", next(reader)[:-1], rename=True)
                for row in reader:
                    gt_data = GTData(*row)
                    if gt_data.success == 'N':
                        gt_success = [
                                g for g in gt_datas if
                                    (g.location == gt_data.location) &
                                    (g.imt==gt_data.imt) &
                                    (g.vs30==gt_data.vs30) &
                                    (g.poe==gt_data.poe) & 
                                    (g.success=='Y')
                        ]
                        if not gt_success:
                            gt_config, disagg_config = next(generate_gt_configs(
                                task_args,
                                [gt_data.location],
                                [gt_data.poe],
                                [gt_data.vs30],
                                [gt_data.imt]))
                            gt_id = launch_gt(gt_config) 
                            now = dt.datetime.now(dt.datetime.now().astimezone().tzinfo)
                            disagg_writer.writerow([gt_id, now.date().isoformat(), now.time().isoformat('seconds'), now.tzname()] + list(disagg_config))
        else:
            for gt_config, disagg_config in generate_gt_configs(task_args, locations, poes, vs30s, imts): 
                gt_id = launch_gt(gt_config) 
                now = dt.datetime.now(dt.datetime.now().astimezone().tzinfo)
                disagg_writer.writerow([gt_id, now.date().isoformat(), now.time().isoformat('seconds'), now.tzname()] + list(disagg_config))


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="run disaggregations")
    parser.add_argument('-r', '--rerun' , action='store_true', help="rerun the failed jobs in NZSHM22_DISAGG_LIST")
    args = parser.parse_args()

    # CONFIG_FILE = "/home/chrisdc/NSHM/Disaggs/disagg_configs/DUD/deagg_configs_DUD-0.1-PGA-400.json"
    # config_dir = Path('/home/chrisdc/NSHM/Disaggs/Disagg_Targets')

    task_args = dict(
        hazard_model_id = 'SLT_v8_gmm_v2_FINAL',
        agg = 'mean',
        inv_time = 50,
    )

    vs30s = [250, 400, 750]
    imts = ['PGA', 'SA(0.2)', 'SA(0.5)', 'SA(1.5)', 'SA(3.0)']
    # locations = ['AKL','WLG','CHC','DUD'] # [1]
    # locations = ['HLZ','TRG', 'PMR', 'NPE'] #Hamilton, Tauranga, Palmerston North, Napier [2]
    # locations = ['ROT', 'NPL', 'NSN', 'IVC'] #Rotorua, New Plymouth, Nelson, Invercargill [3]
    # locations = ['ZWG', 'GIS', 'BHE', 'TUO' ] #Whanganui, Gisborne, Blenheim, Taupo [4]
    # locations = ['MRO', 'LVN', 'ZQN', 'GMN'] #Masterton, Levin, Queenstown, Greymouth [5]
    # locations = ['HAW', 'KBZ', 'KKE', 'MON'] #Hawera, Kaikoura, Kerikeri, Mount Cook [6]
    # locations = ['TEU', 'TIU', 'TKZ', 'TMZ'] #Te Anau, Timaru, Tokoroa, Thames [7]
    # locations = ['WHK', 'WHO', 'WSZ', 'ZTR'] #Whakatane, Franz Josef, Westport, Turangi [8]
    locations = ['ZOT', 'ZHT', 'ZHS'] #Otira, Haast, Hanmer Springs [9]

    # poes = [0.86, 0.63, 0.39, 0.18, 0.1, 0.05, 0.02] [SRWG]
    # poes = [0.1, 0.02] [1]
    poes = [0.86, 0.63, 0.39] # [2]
    gt_filename = 'loc9_vs301_imt1_poe2.csv'    
    # gt_filename = 'test_rerun.csv'

    run_main(task_args, locations, imts, vs30s, poes, gt_filename, args.rerun)

