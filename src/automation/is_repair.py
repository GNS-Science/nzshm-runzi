"""
Script to repaira set of 150 inversions that completed on beavan but errored on mfd_table extraction.

SO the final transfer never completed.

Pseudo-code:

 - iterate the InvSol*.zip files in ../work , extracting the ID for their RGT task from their name (whew)
 - for each IS file:
  - call the API to fetch the arguments values from the RGT
  - upload the IS to API with the meta-data

"""
import argparse
import json
import git
import os
import uuid
from pathlib import Path
import platform
import time
import fnmatch

import datetime as dt
from dateutil.tz import tzutc
from types import SimpleNamespace

from nshm_toshi_client.rupture_generation_task import RuptureGenerationTask
from nshm_toshi_client.general_task import GeneralTask
from nshm_toshi_client.task_relation import TaskRelation

from src.automation.scaling.toshi_api import ToshiApi

# Set up your local config, from environment variables, with some sone defaults
from scaling.local_config import (OPENSHA_ROOT, WORK_PATH, OPENSHA_JRE, FATJAR,
    JVM_HEAP_MAX, JVM_HEAP_START, USE_API, JAVA_THREADS,
    API_KEY, API_URL, S3_URL, CLUSTER_MODE)

class RepairTask():
    """
    COnfigure the python client for a InversionTask
    """
    def __init__(self):
        headers={"x-api-key":API_KEY}
        #self._ruptgen_api = RuptureGenerationTask(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
        #self._general_api = GeneralTask(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
        #self._task_relation_api = TaskRelation(API_URL, None, with_schema_validation=True, headers=headers)
        self._toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=False, headers=headers)


    def run(self, task_id):

        t0 = dt.datetime.utcnow()

        #create new task in toshi_api
        gen_task = self._toshi_api.get_rgt_task(task_id)
        meta = dict()
        for kv in gen_task['arguments']:
            meta[kv['k']] = kv['v']

        # print(meta)
        output_file = Path(WORK_PATH, f"NZSHM22_InversionSolution-{task_id}.zip")
        assert output_file.exists()

        self._toshi_api.inversion_solution.upload_inversion_solution(task_id, filepath=output_file, mfd_table=None,
             meta=meta, metrics=None)
        os.rename(output_file, str(output_file) + '.DONE')
        print(task_id, ": took %s secs" % (dt.datetime.utcnow() - t0).total_seconds())

if __name__ == "__main__":

    #list files in work path matching the criteria
    def get_task_ids():
        for root, dirs, files in os.walk(WORK_PATH):
            for filename in fnmatch.filter(files, "NZSHM22_InversionSolution-*.zip"):
                yield filename[26:-4]

    count = 0
    for task_id in get_task_ids():
        print(task_id)
        task = RepairTask()
        task.run(task_id)
        count += 1

    print(f'Done, pushed {count} files')