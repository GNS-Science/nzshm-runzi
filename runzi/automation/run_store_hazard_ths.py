import json
import datetime as dt
from pathlib import Path
import tempfile
from zipfile import ZipFile
from collections import namedtuple

from openquake.commonlib import datastore
from toshi_hazard_store.oq_import import export_meta_v3, export_rlzs_v3

from runzi.automation.scaling.hazard_output_helper import HazardOutputHelper
from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.automation.scaling.local_config import (API_KEY, API_URL, WORK_PATH)
from runzi.automation.run_gt_index import parse_task_args


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

LOCATIONS_ID = 'ALL'

def extract_and_save(hdf5_path, toshi_gt_id, toshi_hazard_id, inv_id, bg_id, tag_str):
    """Do the work."""

    hdf5_path = Path(hdf5_path)
    assert hdf5_path.exists()
    dstore = datastore.DataStore(str(hdf5_path))

    # Save metadata record
    t0 = dt.datetime.utcnow()
    print('Begin saving meta')

    tags = [tag.strip() for tag in tag_str.split(',')]
    srcs = [inv_id, bg_id]

    print(tags, srcs)

    meta = export_meta_v3(dstore, toshi_hazard_id, toshi_gt_id, LOCATIONS_ID, tags, srcs)

    print("Done saving meta, took %s secs" % (dt.datetime.utcnow() - t0).total_seconds())

    t0 = dt.datetime.utcnow()
    print('Begin saving realisations (V3)')
    export_rlzs_v3(dstore, meta)

    t1 = dt.datetime.utcnow()
    print("Done saving realisations, took %s secs" % (t1 - t0).total_seconds())
    print(f"Saved realizations for HazardSolution {toshi_hazard_id} from GeneralTask {toshi_gt_id}")

    dstore.close()


def dowload_and_save(gt_id, hazard_soln_id, inv_id, bg_id, tag):
    
    hazard_helper = HazardOutputHelper(toshi_api)
    downloads = hazard_helper.download_hdf([hazard_soln_id], WORK_PATH)

    for hdf5_id, info in downloads.items():

        archive_filepath = info['filepath']
        with ZipFile(archive_filepath) as archive_file:
            if len(archive_file.namelist()) != 1:
                raise Exception('more than one file found in %s' % archive_filepath)
            hdf_file = archive_file.namelist()[0]
            with tempfile.TemporaryDirectory() as tmpdirname:
                hdf5_filepath = archive_file.extract(hdf_file, tmpdirname)
                extract_and_save(hdf5_filepath, gt_id, hazard_soln_id, inv_id, bg_id, tag)



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

def save_gts(gt_ids, toshi_api):

    for gt_id in gt_ids:
        gt_info = get_hazard_info(toshi_api, gt_id)
        for task in gt_info['children']['edges']:
            oq_hazard_task = task['node']['child']

            if (oq_hazard_task['state'] != 'DONE') and (oq_hazard_task['status'] != 'SUCCESS'):
                tid = oq_hazard_task['id']
                msg = f'OpenquakeHazardTask {tid} from GeneralTask {gt_id} does not have "DONE" state and "SUCCESS" status'
                raise Exception(msg)
            hazard_soln_id = oq_hazard_task['hazard_solution']['id']
            args = parse_task_args(oq_hazard_task['arguments'])
            ltp = json.loads(args['logic_tree_permutations'].replace("'",'"'))
            tag_str = ltp[0]['permute'][0]['members'][0]['tag']
            inv_id = ltp[0]['permute'][0]['members'][0]['inv_id']
            bg_id = ltp[0]['permute'][0]['members'][0]['bg_id']

            dowload_and_save(gt_id, hazard_soln_id, inv_id, bg_id, tag_str)
            assert 0

if __name__ == "__main__":

    gt_ids = GT_IDS
    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)
    save_gts(gt_ids, toshi_api)

