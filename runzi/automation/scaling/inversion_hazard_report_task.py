import argparse
import copy
import datetime as dt
import itertools
import json
import time
import urllib
from pathlib import Path, PurePath

import git
from py4j.java_gateway import GatewayParameters, JavaGateway

# Set up local config, from environment variables, with some some defaults
from runzi.automation.scaling.local_config import API_KEY, API_URL, S3_URL, WORK_PATH
from runzi.automation.scaling.toshi_api import ToshiApi

# from runzi.automation.hazPlot import plotHazardCurve


class BuilderTask:
    """
    The python client for a Diagnostics Report
    """

    def __init__(self, job_args):

        self.use_api = job_args.get('use_api', False)

        if self.use_api:
            self._toshi_api = ToshiApi(
                API_URL, S3_URL, None, with_schema_validation=True, headers={"x-api-key": API_KEY}
            )

        # setup the java gateway binding
        self._gateway = JavaGateway(gateway_parameters=GatewayParameters(port=job_args['java_gateway_port']))
        self._hazard_builder = self._gateway.entry_point.getHazardCalculatorBuilder()
        self._output_folder = PurePath(WORK_PATH)  # job_args.get('working_path'))
        self.grid_iml_periods = [0, 0.5, 0.75, 1.0, 2.0]

    def run(self, task_arguments, job_arguments):

        t0 = dt.datetime.utcnow()
        print(f"Starting Task at {dt.datetime.utcnow().isoformat()}")
        ta, ja = task_arguments, job_arguments

        subtask_arguments = ta['subtask_arguments']  # this is a dict of the parameters to run on each

        site_dimensions = list()
        grid_dimensions = list()
        for k, vals in subtask_arguments.items():
            dim = dict(k=k, v=[str(v) for v in vals])
            site_dimensions.append(copy.copy(dim))
            if dim['k'] == 'iml_periods':
                dim['v'] = [str(v) for v in self.grid_iml_periods]
            grid_dimensions.append(copy.copy(dim))

        argument_names = list(subtask_arguments.keys())
        argument_vals = [subtask_arguments[k] for k in argument_names]

        sites_table_data = []
        grid_table_data = []

        for argument_set in itertools.product(*argument_vals):
            named_args = dict()
            for ik in range(len(argument_names)):
                arg_name = argument_names[ik]
                named_args[arg_name] = argument_set[ik]

            t1 = dt.datetime.utcnow()
            self.setup_builder(ta, **named_args)
            calculator = self._hazard_builder.build()

            sites_table_data += [row for row in self.run_sites(ta, calculator, **named_args)]

            t2 = dt.datetime.utcnow()
            print("Site calcs ran in %s secs" % (t2 - t1).total_seconds())

        #     grid_table_data += [row for row in self.run_gridded(ta, calculator, **named_args)]
        #     t3 = dt.datetime.utcnow()
        #     print("Grid calcs ran in %s secs" % (t3-t2).total_seconds())

        # #SAVE TO API Gridded
        # if self.use_api and grid_table_data:
        #     result = self._toshi_api.table.create_table(
        #         grid_table_data,
        #         column_headers = ["forecast_timespan", "bg_seismicity", "iml_period", "gmpe", "lat", "lon", "PofET 0.02", "PofET 0.1"],
        #         column_types = ["double", "string", "double", "string", "double", "double", "double", "double"],
        #         object_id=ta['file_id'],
        #         table_name="Inversion Solution Gridded Hazard",
        #         table_type="HAZARD_GRIDDED",
        #         dimensions=grid_dimensions
        #     )
        #     grid_table_id = result['id']

        #     result = self._toshi_api.inversion_solution.append_hazard_table(ta['file_id'], grid_table_id,
        #         label= "Inversion Solution Gridded Hazard",
        #         table_type="HAZARD_GRIDDED",
        #         dimensions=grid_dimensions
        #     )
        #     print("created & linked gridded table: ", grid_table_id)

        # SAVE TO API sites
        if self.use_api and sites_table_data:
            result = self._toshi_api.table.create_table(
                sites_table_data,
                column_headers=[
                    "forecast_timespan",
                    "bg_seismicity",
                    "iml_period",
                    "gmpe",
                    "location",
                    "lat",
                    "lon",
                    "x",
                    "y",
                ],
                column_types=["double", "string", "double", "string", "string", "double", "double", "double", "double"],
                object_id=ta['file_id'],
                table_name="Inversion Solution Site Hazard",
                table_type="HAZARD_SITES",
                dimensions=site_dimensions,
            )
            sites_table_id = result['id']
            result = self._toshi_api.inversion_solution.append_hazard_table(
                ta['file_id'],
                sites_table_id,
                label="Inversion Solution Site Hazard",
                table_type="HAZARD_SITES",
                dimensions=site_dimensions,
            )
            print("created & linked sites table: ", sites_table_id)

        t4 = dt.datetime.utcnow()
        print("Task took %s secs" % (t4 - t0).total_seconds())

    def setup_builder(
        self, ta, forecast_timespans, bg_seismicitys, iml_periods, gmpes, grid_spacings, regions, **kwargs
    ):

        file_path = PurePath(WORK_PATH, 'downloads', ta['file_id'], ta['file_name'])

        self._hazard_builder.setSolutionFile(str(file_path)).setLinear(True).setForecastTimespan(
            float(forecast_timespans)
        ).setIntensityMeasurePeriod(float(iml_periods)).setBackgroundOption(bg_seismicitys)

    def run_gridded(
        self, ta, calculator, forecast_timespans, bg_seismicitys, iml_periods, gmpes, grid_spacings, regions
    ):
        # gridded
        gridCalc = self._gateway.entry_point.getGridHazardCalculator(calculator)
        gridCalc.setRegion(regions)
        gridCalc.setSpacing(float(grid_spacings))
        # gridCalc.createGeoJson(0, "/tmp/gridded-hazard.json");
        if not iml_periods in self.grid_iml_periods:
            return

        table_rows = gridCalc.getTabularGridHazards()
        args = [
            forecast_timespans,
            bg_seismicitys,
            iml_periods,
            gmpes,
        ]
        header = table_rows[0]

        for row in table_rows[1:]:
            newrow = args + [x for x in row][:4]
            yield newrow

        print('gridded e.g. rwo ', newrow)

    def run_sites(self, ta, calculator, forecast_timespans, bg_seismicitys, iml_periods, gmpes, **kwargs):

        ####
        # Site Hazard plots
        ####

        # from google/latlon.net
        locations = dict(
            WN=["Wellington", -41.276825, 174.777969],  # -41.288889, 174.777222], OAkley
            AK=["Auckland", -36.848461, 174.763336],
            GN=["Gisborne", -38.662334, 178.017654],
            CC=["Christchurch", -43.525650, 172.639847],
        )

        # plot_folder = Path(self._output_folder, ta['file_id'])
        # plot_folder.mkdir(exist_ok=True)

        print(f'location reports')
        for code in locations.keys():
            point = locations[code][1:3]
            # years = iml_periods
            # group = 'crustal'
            # gmpe = gmpes

            # table = [row[:2] for row in calculator.tabulariseCalc(*point)]
            args = [
                forecast_timespans,
                bg_seismicitys,
                iml_periods,
                gmpes,
            ]
            table = [row[:2] for row in calculator.tabulariseCalc(*point)]
            for row in table:
                yield args + locations[code] + list(row)

            # print(code, table)
            # plotHazardCurve(table,
            #     years=years,
            #     title=f"opensha: {locations[code][0]} {group} PGA hazard ({years} year)",
            #     subtitle=f"{ta['file_id']}",
            #     fileName= PurePath(plot_folder, f"{ta['file_id']}_{code}_hazard_plot_{years}yr.png"))

    def save_table(self, ta, table_rows):
        column_headers = table_rows[0]
        column_types = ["double" for x in table_rows[0]]
        result = self._toshi_api.table.create_table(
            table_rows[1:],
            column_headers,
            column_types,
            object_id=ta['file_id'],
            table_name="Inversion Solution Gridded Hazard",
            table_type="HAZARD_GRIDDED",
            dimensions=[
                {"k": "grid_spacing", "v": ["0.5"]},
                {"k": "region", "v": ["NZ_TEST_GRIDDED"]},
                {"k": "iml_period", "v": ["1.0"]},
            ],
        )

        mfd_table_id = result['id']
        print("created table: ", result['id'])

        result = self._toshi_api.inversion_solution.append_hazard_table(
            ta['file_id'],
            mfd_table_id,
            label="Inversion Solution Gridded Hazard",
            table_type="HAZARD_GRIDDED",
            dimensions=[
                {"k": "grid_spacing", "v": ["0.5"]},
                {"k": "region", "v": ["NZ_TEST_GRIDDED"]},
                {"k": "iml_period", "v": ["1.0"]},
            ],
        )
        # print("append_hazard_table result", result)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    args = parser.parse_args()

    try:
        # LOCAL and CLUSTER this is a file
        config_file = args.config
        f = open(args.config, 'r', encoding='utf-8')
        config = json.load(f)
    except:
        # for AWS this must be a quoted JSON string
        config = json.loads(urllib.parse.unquote(args.config))

    # maybe the JVM App is a little slow to get listening
    time.sleep(2)
    # Wait for some more time, scaled by taskid to avoid S3 consistency issue
    # time.sleep(config['job_arguments']['task_id'] )

    # print(config)
    task = BuilderTask(config['job_arguments'])
    task.run(**config)
