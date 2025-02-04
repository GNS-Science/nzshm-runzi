import datetime as dt
import json
import logging
import multiprocessing
import sys
import tempfile
import time
from collections import namedtuple
from pathlib import Path
from typing import List
from zipfile import ZipFile

from openquake.commonlib import datastore
from toshi_hazard_store.oq_import import export_meta_v3, export_rlzs_v3

from runzi.automation.run_gt_index import parse_task_args
from runzi.automation.scaling.hazard_output_helper import HazardOutputHelper
from runzi.automation.scaling.local_config import API_KEY, API_URL, WORK_PATH
from runzi.automation.scaling.toshi_api import ToshiApi

log = logging.getLogger()
logging.basicConfig(level=logging.INFO)
logging.getLogger('gql.transport.requests').setLevel(logging.WARN)

formatter = logging.Formatter(fmt='%(asctime)s %(levelname)-8s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
screen_handler = logging.StreamHandler(stream=sys.stdout)
screen_handler.setFormatter(formatter)
log.addHandler(screen_handler)

GT_IDS = [
    "R2VuZXJhbFRhc2s6MjkyMzY2Nw==",
    "R2VuZXJhbFRhc2s6MjkyMzc2Mg==",
    "R2VuZXJhbFRhc2s6MjkyMzc2Nw==",
    "R2VuZXJhbFRhc2s6MjkyMzc2OA==",
    "R2VuZXJhbFRhc2s6MjkyMzg0Mw==",
    "R2VuZXJhbFRhc2s6MjkyMzkwMA==",
    "R2VuZXJhbFRhc2s6MjkyMzkwMQ==",
    "R2VuZXJhbFRhc2s6MjkyMzk1OQ==",
    "R2VuZXJhbFRhc2s6MjkyMzk2Nw==",
]
white_list = ['T3BlbnF1YWtlSGF6YXJkU29sdXRpb246MjkyNDM1MA==']

LOCATIONS_ID = 'ALL'

NUM_EXPECTED_BRANCHES = 49
NUM_WORKERS = 20

HazardSolution = namedtuple("HazardSolution", "gt_id hazard_soln_id inv_id bg_id tag_str")


class THSWorkerMP(multiprocessing.Process):

    def __init__(self, task_queue: multiprocessing.JoinableQueue, result_queue: multiprocessing.Queue):
        multiprocessing.Process.__init__(self)
        self.task_queue = task_queue
        self.result_queue = result_queue

    def run(self):
        log.info("worker %s running." % self.name)
        proc_name = self.name

        while True:
            nt = self.task_queue.get()
            if nt is None:
                # Poison pill means shutdown
                self.task_queue.task_done()
                log.info('%s: Exiting' % proc_name)
                break

            log.info(f"worker {self.name} starting download_and_save() for {nt}")
            rnt = dowload_and_save(nt)
            self.task_queue.task_done()
            log.info('%s task done' % self.name)
            self.result_queue.put(rnt)


def batch_save(haz_solns: List[HazardSolution], num_workers):

    task_queue: multiprocessing.JoinableQueue = multiprocessing.JoinableQueue()
    result_queue: multiprocessing.Queue = multiprocessing.Queue()

    log.info('Creating %d workers' % num_workers)
    workers = [THSWorkerMP(task_queue, result_queue) for i in range(num_workers)]
    for w in workers:
        w.start()
    # Enqueue jobs
    num_jobs = 0
    for haz_soln in haz_solns:
        if white_list and (haz_soln.hazard_soln_id not in white_list):
            continue
        task_queue.put(haz_soln)
        log.info('sleeping 10 seconds before queuing next task')
        time.sleep(10)
        num_jobs += 1

    for i in range(num_workers):
        task_queue.put(None)

    task_queue.join()

    results = []
    while num_jobs:
        result = result_queue.get()
        results.append(result)
        num_jobs -= 1

    return results


def dowload_and_save(haz_soln: HazardSolution):

    hazard_helper = HazardOutputHelper(toshi_api)
    downloads = hazard_helper.download_hdf([haz_soln.hazard_soln_id], WORK_PATH)

    for hdf5_id, info in downloads.items():

        archive_filepath = info['filepath']
        with ZipFile(archive_filepath) as archive_file:
            if len(archive_file.namelist()) != 1:
                raise Exception('more than one file found in %s' % archive_filepath)
            hdf_file = archive_file.namelist()[0]
            with tempfile.TemporaryDirectory(dir=WORK_PATH) as tmpdirname:
                hdf5_filepath = archive_file.extract(hdf_file, tmpdirname)
                log.info(f'hdf5_filepath: {hdf5_filepath}')
                extract_and_save(
                    hdf5_filepath,
                    haz_soln.gt_id,
                    haz_soln.hazard_soln_id,
                    haz_soln.inv_id,
                    haz_soln.bg_id,
                    haz_soln.tag_str,
                )

    return haz_soln


def extract_and_save(hdf5_path, toshi_gt_id, toshi_hazard_id, inv_id, bg_id, tag_str):
    """Do the work."""

    hdf5_path = Path(hdf5_path)
    assert hdf5_path.exists()
    dstore = datastore.DataStore(str(hdf5_path))

    # Save metadata record
    t0 = dt.datetime.utcnow()
    log.info('Begin saving meta')

    tags = [tag.strip() for tag in tag_str.split(',')]
    srcs = [inv_id, bg_id]

    print(tags, srcs)

    meta = export_meta_v3(dstore, toshi_hazard_id, toshi_gt_id, LOCATIONS_ID, tags, srcs)

    log.info("Done saving meta, took %s secs" % (dt.datetime.utcnow() - t0).total_seconds())

    t0 = dt.datetime.utcnow()
    log.info('Begin saving realisations (V3)')
    export_rlzs_v3(dstore, meta)

    t1 = dt.datetime.utcnow()
    log.info("Done saving realisations, took %s secs" % (t1 - t0).total_seconds())
    log.info(f"Saved realizations for HazardSolution {toshi_hazard_id} from GeneralTask {toshi_gt_id}")

    dstore.close()


def get_hazard_info(toshi_api, gt_id):

    qry = '''
        query haz_info_from_gt ($id:ID!) {
            node(id: $id) {
            id
            ... on GeneralTask {
                children {
                edges {
                    
                    node {
                    child {
                        __typename
                        ... on OpenquakeHazardTask {
                        id
                        state
                        result
                        arguments {
                            k v
                        }
                        metrics {
                            k v
                        }
                        hazard_solution {
                            id                           
                        }
                        }
                    }
                    }
                }
                }
            }
            }
            }'''

    input_variables = dict(id=gt_id)
    executed = toshi_api.run_query(qry, input_variables)
    return executed['node']


def get_haz_solns(gt_ids, toshi_api):

    haz_solns = []
    for gt_id in gt_ids:
        gt_info = get_hazard_info(toshi_api, gt_id)
        num_sucess_branches = 0
        for task in gt_info['children']['edges']:

            oq_hazard_task = task['node']['child']
            if (oq_hazard_task['state'] != 'DONE') and (oq_hazard_task['status'] != 'SUCCESS'):
                tid = oq_hazard_task['id']
                msg = f'OpenquakeHazardTask {tid} from GeneralTask {gt_id} does not have "DONE" state and "SUCCESS" status'
                raise Exception(msg)
            else:
                num_sucess_branches += 1

            metrics = parse_task_args(oq_hazard_task['metrics'])
            if metrics.get('no_result') == 'TRUE':
                continue

            hazard_soln_id = oq_hazard_task['hazard_solution']['id']
            args = parse_task_args(oq_hazard_task['arguments'])
            ltp = json.loads(args['logic_tree_permutations'].replace("'", '"'))
            tag_str = ltp[0]['permute'][0]['members'][0]['tag']
            inv_id = ltp[0]['permute'][0]['members'][0]['inv_id']
            bg_id = ltp[0]['permute'][0]['members'][0]['bg_id']

            haz_solns.append(
                HazardSolution(
                    gt_id=gt_id,
                    hazard_soln_id=hazard_soln_id,
                    inv_id=inv_id,
                    bg_id=bg_id,
                    tag_str=tag_str,
                )
            )

        if num_sucess_branches != NUM_EXPECTED_BRANCHES:
            msg = f'Missing {NUM_EXPECTED_BRANCHES - num_sucess_branches} branches from GeneralTask {gt_id}'
            raise Exception

    return haz_solns


if __name__ == "__main__":

    gt_ids = GT_IDS
    headers = {"x-api-key": API_KEY}
    toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)
    haz_solns = get_haz_solns(gt_ids, toshi_api)
    print('')
    print('hazard solutions:')
    print(*haz_solns, sep='\n')
    batch_save(haz_solns, NUM_WORKERS)
