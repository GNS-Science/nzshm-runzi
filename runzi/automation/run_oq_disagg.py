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

from nzshm_common.location.location import location_by_id, LOCATION_LISTS
from nzshm_common.grids import load_grid
from nzshm_common.location.code_location import CodedLocation


from runzi.automation.scaling.toshi_api import ToshiApi, CreateGeneralTaskArgs, SubtaskType, ModelType
from runzi.configuration.oq_disagg import build_hazard_tasks, get_disagg_configs
from runzi.automation.scaling.schedule_tasks import schedule_tasks

from runzi.automation.scaling.local_config import (WORK_PATH, USE_API, JAVA_THREADS,
    API_KEY, API_URL, CLUSTER_MODE, EnvMode )

from runzi.CONFIG.OQ.SLT_v9p0p0 import logic_tree_permutations as logic_trees
# If you wish to override something in the main config, do so here ..
WORKER_POOL_SIZE = 1
# USE_API = False

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
    TASK_DESCRIPTION = f"hazard ID: {gt_config['hazard_model_id']}, hazard aggregation target: {gt_config['agg']}"

    # disagg_settings = dict(mag_bin_width = 0.499)
    # disagg_settings = dict(mag_bin_width = 0.5)
    disagg_settings = dict(
        disagg_bin_edges = {'dist': [0, 5.0, 10.0, 15.0, 20.0, 30.0, 40.0, 50.0, 60.0, 80.0, 100.0, 140.0, 180.0, 220.0, 260.0, 320.0, 380.0, 500.0]},
        num_epsilon_bins = 16,
        mag_bin_width = .1999,
        coordinate_bin_width = 5,
        disagg_outputs = "TRT Mag Dist Mag_Dist TRT_Mag_Dist_Eps"
        # disagg_outputs = "TRT Mag Dist Mag_Dist Mag_Dist_TRT_Eps"
    )

    disagg_configs = get_disagg_configs(gt_config, logic_trees)
    for disagg_config in disagg_configs:
        disagg_config['disagg_settings'] = disagg_settings

    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)

    # TODO obtain the config (job.ini from the first nearest_rlz)
    hazard_config = "RmlsZToyODQ4OTc1" # GSIM LT v2, no sites, renew 2023-04-29
            

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
        yield dict(task_args,
            location = loc,
            poe = poe,
            vs30 = vs30,
            imt = imt,
        )


# def generate_single_gt_config(task_args, config):

#     loc = config['location']
#     poe = config['poe']
#     vs30 = config['vs30']
#     imt = config['imt']

#     breakpoint()
#     return dict(
#         location = loc,
#         poe = poe,
#         vs30 = vs30,
#         imt = imt,
#         inv_time = task_args['inv_time'],
#         agg = task_args['agg'],
#         hazard_model_id = task_args['hazard_model_id'],
#         rupture_mesh_spacing = task_args['rupture_mesh_spacing'],
#         ps_grid_spacing = task_args['ps_grid_spacing'],
#     ) 

def run_main(task_args, locations, imts, vs30s, poes, gt_filename):

    # gt_filepath = Path(gt_filename)

    # if gt_filepath.exists(): 
    #     raise Exception('file %s already exists, cannot overwrite' % gt_filepath)

    # with open(gt_filepath, 'w') as df:
    #     disagg_writer = csv.writer(df)
    #     disagg_writer.writerow(['GT_ID', 'date', 'time', 'time_zone'] + list(Disagg._fields))
    #     if rerun['rerun']:
    #         DISAGG_LIST = os.environ['NZSHM22_DISAGG_LIST']
    #         with open(DISAGG_LIST, 'r') as gt_list_file:
    #             reader = csv.reader(gt_list_file)
    #             gt_datas = []
    #             GTData = namedtuple("GTData", next(reader)[:-1], rename=True)
    #             for row in reader:
    #                 gt_datas.append(GTData(*row))
            

    #         with open(DISAGG_LIST, 'r') as gt_list_file:
    #             reader = csv.reader(gt_list_file)
    #             GTData = namedtuple("GTData", next(reader)[:-1], rename=True)
    #             for row in reader:
    #                 gt_data = GTData(*row)
    #                 if gt_data.success == 'N':
    #                     gt_success = [
    #                             g for g in gt_datas if
    #                                 (g.location == gt_data.location) &
    #                                 (g.imt==gt_data.imt) &
    #                                 (g.vs30==gt_data.vs30) &
    #                                 (g.poe==gt_data.poe) & 
    #                                 (g.success=='Y')
    #                     ]
    #                     if not gt_success:
    #                         gt_config, disagg_config = next(generate_gt_configs(
    #                             task_args,
    #                             [gt_data.location],
    #                             [float(gt_data.poe)],
    #                             [int(gt_data.vs30)],
    #                             [gt_data.imt]))
    #                         if rerun['dry']:
    #                             print(gt_config, disagg_config)
    #                         else:
    #                             gt_id = launch_gt(gt_config) 
    #                             now = dt.datetime.now(dt.datetime.now().astimezone().tzinfo)
    #                             disagg_writer.writerow([gt_id, now.date().isoformat(), now.time().isoformat('seconds'), now.tzname()] + list(disagg_config))
    #     else:
    gt_ids = []
    with open(gt_filename, 'w', buffering=1) as gtfile:
        for gt_config in generate_gt_configs(task_args, locations, poes, vs30s, imts): 
            gt_id = launch_gt(gt_config)
            gt_ids.append(gt_id)
            # now = dt.datetime.now(dt.datetime.now().astimezone().tzinfo)
            # disagg_writer.writerow([gt_id, now.date().isoformat(), now.time().isoformat('seconds'), now.tzname()] + list(disagg_config))
            gtfile.write(gt_id + '\n')
    return gt_ids


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="run disaggregations")
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-r', '--rerun' , action='store_true', help="rerun the failed jobs in NZSHM22_DISAGG_LIST")
    group.add_argument('-d', '--dry-rerun' , action='store_true', help="print what jobs would be rerun if --rerun were used but don't run them")
    args = parser.parse_args()
    rerun = {'rerun': args.rerun | args.dry_rerun, 'dry': args.dry_rerun}

    task_args = dict(
        hazard_model_id = 'NSHM_v1.0.4',
        agg = 'mean',
        inv_time = 50,
        rupture_mesh_spacing = 4,
        ps_grid_spacing = 30, #km 
    )

    # locations = LOCATION_LISTS['SRWG214']['locations'] + LOCATION_LISTS['NZ']['locations']
    # locations = LOCATION_LISTS['NZ']['locations'] + ['srg_164']
    # locations = ['WLG']
    # locations = LOCATION_LISTS['NZ']['locations']
    # locations = ['srg_164']
    grid_01 = set([CodedLocation(*pt, 0.001).code for pt in load_grid('NZ_0_1_NB_1_1')])
    grid_02 = set([CodedLocation(*pt, 0.001).code for pt in load_grid('NZ_0_2_NB_1_1')])
    # locations = list(grid_01.intersection(grid_02))
    locations = list(grid_01.difference(grid_02))
    locations.sort()
    h = int(len(locations)/2)
    locations = locations[h:]


    # poes = [0.02, 0.05, 0.10, 0.18, 0.39, 0.63, 0.86]
    poes = [0.02]
    imts = ['PGA']
    vs30s = [275]
    gt_filename = 'gtids_griddiffB_02.txt'

    gt_ids = run_main(task_args, locations, imts, vs30s, poes, gt_filename)


    print("_____________________GT IDs______________________")
    for id in gt_ids:
        print(id)