#!python3 oq_opensha_hazard_task.py

import os
import sys
from pathlib import Path


class BuilderTask():

    def __init__(self, job_args):

        self.use_api = job_args.get('use_api', False)
        self._output_folder = PurePath(job_args.get('working_path'))


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


        # Run the task....
        src_folder = Path(self._output_folder, ta['file_id'])
        src_folder.mkdir(parents=True, exist_ok=True)

        ## print(config)
        ## following are from Marco's convert example
        # folder = './NZSHM22_InversionSolution-QXV0b21hdGlvblRhc2s6NDE2NTcyMlJH'
        # out_folder = "/WORKING"

        # TOML = """
        # type = 'geojson'
        # source_id = 'SW52ZXJzaW9uU29sdXRpb246MTE4OTcuMGFjYk5Q'
        # source_name = 'nzshm-opensha Hikurangi demo'

        # # Unit of measure for the rupture sampling: km
        # rupture_sampling_distance = 0.5

        # # The `tectonic_region_type` label must be consistent with what you use in the
        # # logic tree for the ground-motion characterisation
        # # Use "Subduction Interface" or "Active Shallow Crust"
        # tectonic_region_type = "Subduction Interface"

        # # Unit of measure for the `investigation_time`: years
        # investigation_time = 1.0
        # """

        # fpath = Path(folder)
        # config = toml.loads(TOML)

        dip_sd = ta['rupture_sampling_distance']
        strike_sd = dip_sd

        source_id = ta['file_id']
        source_name = ta['file_id']
        tectonic_region_type = ta['tectonic_region_type']
        investigation_time = ta['investigation_time']

        computed = get_multi_fault_source(src_folder, dip_sd, strike_sd, source_id,
                                                  source_name, tectonic_region_type,
                                                  investigation_time)

        print(computed)
        Path(out_folder).mkdir(parents=True, exist_ok=True)
        out_file = os.path.join(out_folder, f'{source_id}-ruptures.xml')
        write_source_model(out_file, [computed], name=source_name, investigation_time=investigation_time)
        print('Created output in: {:s}'.format(out_folder))

        t1 = dt.datetime.utcnow()
        print("Conversion took %s secs" % (t1-t0).total_seconds())

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

    task = BuilderTask(config['job_arguments'])
    task.run(**config)

