import argparse
import json
import git
import time
import datetime as dt
from pathlib import PurePath, Path
from py4j.java_gateway import JavaGateway, GatewayParameters
from src.automation.scaling.toshi_api import ToshiApi

# Set up local config, from environment variables, with some some defaults
from src.automation.scaling.local_config import (API_KEY, API_URL, S3_URL)
from src.automation.hazPlot import plotHazardCurve

class BuilderTask():
    """
    The python client for a Diagnostics Report
    """
    def __init__(self, job_args):

        self.use_api = job_args.get('use_api', False)

        if self.use_api:
            self._toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers={"x-api-key":API_KEY})

        #setup the java gateway binding
        self._gateway = JavaGateway(gateway_parameters=GatewayParameters(port=job_args['java_gateway_port']))
        self._hazard_builder = self._gateway.entry_point.getHazardCalculatorBuilder()
        self._output_folder = PurePath(job_args.get('working_path'))

    def run(self, task_arguments, job_arguments):

        t0 = dt.datetime.utcnow()
        print(f"Starting Task at {dt.datetime.utcnow().isoformat()}")

        # Run the task....
        ta, ja = task_arguments, job_arguments

        self._hazard_builder\
            .setSolutionFile(ta['file_path'])\
            .setLinear(True)\
            .setForecastTimespan(float(50))

        calculator = self._hazard_builder.build();

        #gridded
        gridCalc = self._gateway.entry_point.getGridHazardCalculator(calculator)
        gridCalc.setRegion("NZ_TEST_GRIDDED");
        gridCalc.setSpacing(0.5);
        gridCalc.createGeoJson(0, "/tmp/gridded-hazard.json");

        if self.use_api:
            table_rows = []
            for row in gridCalc.getTabularGridHazards():
                table_rows.append([x for x in row])

            column_headers = table_rows[0]
            column_types = ["double" for x in table_rows[0]]
            result = self._toshi_api.create_table(table_rows[1:], column_headers, column_types,
                object_id=ta['file_id'] ,
                table_name="Inversion Solution Gridded Hazard",
                table_type="HAZARD_GRIDDED",
                dimensions=[
                    {"k": "grid_spacing", "v": ["0.5"]},
                    {"k": "region", "v": ["NZ_TEST_GRIDDED"]},
                    {"k": "iml_period", "v": ["1.0"]},
                    ]
                )

            mfd_table_id = result['id']
            print("created table: ", result['id'])

            result = self._toshi_api.inversion_solution.append_hazard_table(ta['file_id'], mfd_table_id,
                label= "Inversion Solution Gridded Hazard",
                table_type="HAZARD_GRIDDED",
                dimensions=[
                    {"k": "grid_spacing", "v": ["0.5"]},
                    {"k": "region", "v": ["NZ_TEST_GRIDDED"]},
                    {"k": "iml_period", "v": ["1.0"]},
                    ])
            print("append_hazard_table result", result)

        ####
        #Hazard plots
        ####

        #from google/latlon.net
        locations = dict(
            WN = ["Wellington", -41.276825, 174.777969], #-41.288889, 174.777222], OAkley
            AK = ["Auckland", -36.848461, 174.763336],
            GN = ["Gisborne", -38.662334, 178.017654],
            CC = ["Christchurch", -43.525650, 172.639847],
        )

        plot_folder = Path(self._output_folder, ta['file_id'])
        plot_folder.mkdir(exist_ok=True)

        print(f'location reports')
        for code in locations.keys():

            point = locations[code][1:3]
            years = 50
            group = 'crustal'
            gmpe = 'ASK2014'

            table = [row[:2] for row in calculator.tabulariseCalc(*point)]

            print(code, table)
            plotHazardCurve(table,
                years=years,
                title=f"opensha: {locations[code][0]} {group} PGA hazard ({years} year)",
                subtitle=f"{ta['file_id']}",
                fileName= PurePath(plot_folder, f"{ta['file_id']}_{code}_hazard_plot_{years}yr.png"))

        t1 = dt.datetime.utcnow()
        print("Report took %s secs" % (t1-t0).total_seconds())


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    args = parser.parse_args()

    config_file = args.config
    f= open(config_file, 'r', encoding='utf-8')
    config = json.load(f)

    # maybe the JVM App is a little slow to get listening
    time.sleep(2)
    # Wait for some more time, scaled by taskid to avoid S3 consistency issue
    #time.sleep(config['job_arguments']['task_id'] )

    # print(config)
    task = BuilderTask(config['job_arguments'])
    task.run(**config)
