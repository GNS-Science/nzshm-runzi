import argparse
import base64
import datetime as dt
import json
import os
import platform
import time
import urllib
import uuid
from pathlib import Path, PurePath

from dateutil.tz import tzutc
from nshm_toshi_client.task_relation import TaskRelation
from solvis import *

from runzi.automation.scaling.local_config import API_KEY, API_URL, S3_URL, WORK_PATH
from runzi.automation.scaling.toshi_api import ToshiApi

locations = dict(
    Wellington = ["Wellington", -41.276825, 174.777969],
    Auckland = ["Auckland", -36.848461, 174.763336],
    Gisborne = ["Gisborne", -38.662334, 178.017654],
    Christchurch = ["Christchurch", -43.525650, 172.639847],
)

class BuilderTask():
    """
    The python client for a Sub Solution build
    """
    def __init__(self, job_args):

        self.use_api = job_args.get('use_api', False)
        self._output_folder = PurePath(WORK_PATH)

        if self.use_api:
            headers={"x-api-key":API_KEY}
            # self._ruptgen_api = RuptureGenerationTask(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
            self._toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
            self._task_relation_api = TaskRelation(API_URL, None, with_schema_validation=True, headers=headers)


    def run(self, task_arguments, job_arguments):
        # Run the task....
        t0 = dt.datetime.utcnow()
        ta, ja = task_arguments, job_arguments

        environment = {}

        if self.use_api:
            #create new task in toshi_api
            task_id = self._toshi_api.automation_task.create_task(
                dict(
                    created=dt.datetime.now(tzutc()).isoformat(),
                    task_type="INVERSION",
                    model_type=ta['config_type'].upper(),
                    ),
                arguments=task_arguments,
                environment=environment
                )

            #link task to the parent task
            self._task_relation_api.create_task_relation(job_arguments['general_task_id'], task_id)

            #link task to the input solution
            input_file_id = task_arguments.get('solution_id')
            if input_file_id:
                self._toshi_api.automation_task.link_task_file(task_id, input_file_id, 'READ')

        else:
            task_id = str(uuid.uuid4())

        ##DO THE WORK
        result = self.process(
            ja.get("solution_id"),
            ja.get("solution_info").get('filepath'),
            locations.get(ta.get("location")),
            ta.get("radius"),
            ta.get("rate_threshold")
        )


        # SAVE the results
        if self.use_api:
            #record the completed task

            #the geojson
            self._toshi_api.automation_task.upload_task_file(task_id, result["geofile"], 'WRITE')

            # #the python log files
            # python_log_file = self._output_folder.joinpath(f"python_script.{job_arguments['java_gateway_port']}.log")
            # self._toshi_api.automation_task.upload_task_file(task_id, python_log_file, 'WRITE')

            #upload the task output
            inversion_id = self._toshi_api.inversion_solution.upload_inversion_solution(task_id,
                filepath=result['solution'],
                meta=task_arguments, metrics=result['metrics'])
            print("created inversion solution: ", inversion_id)

            done_args = {
             'task_id':task_id,
             'duration':(dt.datetime.utcnow() - t0).total_seconds(),
             'result':"SUCCESS",
             'state':"DONE",
            }
            self._toshi_api.automation_task.complete_task(done_args, result['metrics'])


        t1 = dt.datetime.utcnow()
        print("Report took %s secs" % (t1-t0).total_seconds())


    def process(self, solution_id, solution_filepath, location, radius_m, rate_threshold):

        polygon = circle_polygon(radius_m, location[1], location[2])

        sol = InversionSolution().from_archive(solution_filepath)
        source_rupture_count = sol.rates[sol.rates['Annual Rate']>0].size

        ri = sol.get_ruptures_intersecting(polygon)
        ri_sol = new_sol(sol, ri)

        if rate_threshold:
            ri= rupt_ids_above_rate(ri_sol, rate_threshold)
            ri_sol = new_sol(ri_sol, ri)

        subset_rupture_count = ri_sol.rates[ri_sol.rates['Annual Rate']>0].size

        #wlg_above_sol == new_sol(ri_sol, above)
        sp0 = section_participation(ri_sol, ri)

        #write out a geojson
        radius = f"{int(radius_m/1000)}km"
        geofile = PurePath(WORK_PATH, f"{location[0]}_ruptures_radius({radius})_rate_filter({rate_threshold}).geojson")
        print(f"write new geojson file: {geofile}")
        export_geojson(gpd.GeoDataFrame(sp0), geofile)

        #write the solution

        new_archive = PurePath(WORK_PATH, f"{location[0]}_ruptures_radius({radius})_rate_filter({rate_threshold})_sub_solution.zip")
        print(f"write new solution file: {new_archive}")
        print(f"Filtered InversionSolution {location[0]} within {radius} has {subset_rupture_count} ruptures where rate > {rate_threshold}")
        ri_sol.to_archive(str(new_archive), str(solution_filepath))

        metrics  = dict(subset_rupture_count=subset_rupture_count, source_rupture_count=source_rupture_count)
        return dict(geofile=geofile, solution=new_archive, metrics=metrics)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    args = parser.parse_args()

    try:
        # LOCAL and CLUSTER this is a file
        config_file = args.config
        f= open(args.config, 'r', encoding='utf-8')
        config = json.load(f)
    except:
        # for AWS this must be a quoted JSON string
        config = json.loads(urllib.parse.unquote(args.config))

    # Wait for some more time, scaled by taskid to avoid S3 consistency issue
    time.sleep(config['job_arguments']['task_id'] )

    # print(config)
    task = BuilderTask(config['job_arguments'])
    task.run(**config)

