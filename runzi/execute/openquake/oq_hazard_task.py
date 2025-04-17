"""Openquake Hazard Task."""

# !python3 openquake_hazard_task.py

import argparse
import copy
import csv
import datetime as dt
import json
import logging
import platform
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

from dateutil.tz import tzutc
from nshm_toshi_client import ToshiFile
from nshm_toshi_client.task_relation import TaskRelation
from nzshm_common.geometry.geometry import backarc_polygon, within_polygon
from nzshm_common.location.location import get_locations
from nzshm_model import NshmModel
from nzshm_model.logic_tree import GMCMLogicTree, SourceLogicTree
from nzshm_model.psha_adapter.openquake import OpenquakeConfig, OpenquakeModelPshaAdapter

from runzi.automation.scaling.local_config import API_KEY, API_URL, S3_URL, SPOOF_HAZARD, WORK_PATH
from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.automation.scaling.toshi_api.openquake_hazard.openquake_hazard_task import HazardTaskType
from runzi.execute.openquake.execute_openquake import execute_openquake
from runzi.util.aws import decompress_config

logging.basicConfig(level=logging.DEBUG)

LOG_INFO = logging.INFO
logging.getLogger("py4j.java_gateway").setLevel(LOG_INFO)
logging.getLogger("nshm_toshi_client.toshi_client_base").setLevel(logging.DEBUG)
logging.getLogger("nshm_toshi_client.toshi_file").setLevel(LOG_INFO)
logging.getLogger("urllib3").setLevel(LOG_INFO)
logging.getLogger("botocore").setLevel(LOG_INFO)
logging.getLogger("git.cmd").setLevel(LOG_INFO)
logging.getLogger("gql.transport").setLevel(logging.WARN)

log = logging.getLogger(__name__)


class BuilderTask:
    def __init__(self, job_args):
        self.use_api = job_args.get("use_api", False)

        headers = {"x-api-key": API_KEY}
        self._toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
        self._task_relation_api = TaskRelation(API_URL, None, with_schema_validation=True, headers=headers)

    def _setup_automation_task(self, task_arguments, job_arguments, config_id, environment, task_type) -> str:
        print("=" * 50)
        print("task arguments ...")
        print(task_arguments)
        print("=" * 50)
        automation_task_id = self._toshi_api.openquake_hazard_task.create_task(
            dict(
                created=dt.datetime.now(tzutc()).isoformat(),
                model_type=task_arguments["model_type"].upper(),
                config_id=config_id,
            ),
            arguments=task_arguments,
            environment=environment,
            task_type=task_type,
        )

        # link OpenquakeHazardTask to the parent GT
        gt_conn = self._task_relation_api.create_task_relation(job_arguments["general_task_id"], automation_task_id)
        print(
            f"created task_relationship: {gt_conn} "
            f"for at: {automation_task_id} "
            f"on GT: {job_arguments['general_task_id']}"
        )

        return automation_task_id

    def _store_api_result(
        self,
        automation_task_id,
        task_arguments,
        oq_result,
        config_id,
        modconf_id,
        duration,
    ):
        """Record results in API."""
        ta = task_arguments

        # make a json file from the ta dict so we can save it.
        task_args_json = Path(WORK_PATH, "task_args.json")
        with open(task_args_json, "w") as task_js:
            task_js.write(json.dumps(ta, indent=2))

        # save the json
        task_args_id, post_url = self._toshi_api.file.create_file(task_args_json)
        self._toshi_api.file.upload_content(post_url, task_args_json)
        # save the two output archives
        if not oq_result.get("no_ruptures"):
            csv_archive_id, post_url = self._toshi_api.file.create_file(oq_result["csv_archive"])
            self._toshi_api.file.upload_content(post_url, oq_result["csv_archive"])

            hdf5_archive_id, post_url = self._toshi_api.file.create_file(oq_result["hdf5_archive"])
            self._toshi_api.file.upload_content(post_url, oq_result["hdf5_archive"])

        predecessors = []

        # Save the hazard solution
        if oq_result.get("no_ruptures"):
            solution_id = None
            metrics = {"no_result": "TRUE"}
        else:
            solution_id = self._toshi_api.openquake_hazard_solution.create_solution(
                config_id,
                csv_archive_id,
                hdf5_archive_id,
                produced_by=automation_task_id,
                predecessors=predecessors,
                modconf_id=modconf_id,
                task_args_id=task_args_id,
                meta=task_arguments,
            )
            metrics = dict()

        # update the OpenquakeHazardTask
        self._toshi_api.openquake_hazard_task.complete_task(
            dict(
                task_id=automation_task_id,
                hazard_solution_id=solution_id,
                duration=duration,
                result="SUCCESS",
                state="DONE",
            ),
            metrics=metrics,
        )

        return solution_id

    def set_site_parameters(self, task_arguments: Dict[str, Any]):
        """Set site locations and vs30s for the NshmModel

        Args:
            task_arguments: a dict of task arguments
        """
        if vs30 := task_arguments["site_params"].get("vs30"):
            self.model.hazard_config.set_uniform_site_params(vs30)

        if task_arguments["site_params"].get("locations"):
            locations = get_locations(task_arguments["site_params"]["locations"])
        else:
            with tempfile.TemporaryDirectory() as temp_dir:
                if file_id := task_arguments["site_params"].get("locations_file_id"):
                    headers = {"x-api-key": API_KEY}
                    file_api = ToshiFile(
                        API_URL,
                        None,
                        None,
                        with_schema_validation=True,
                        headers=headers,
                    )
                    file_api.download_file(file_id, target_dir=temp_dir, target_name="sites.csv")
                    locations_file = Path(temp_dir) / "sites.csv"
                else:
                    locations_file = Path(task_arguments["site_params"]["locations_file"])
                locations = get_locations([locations_file])
                with locations_file.open() as lf:
                    reader = csv.reader(lf)
                    header = next(reader)
                    if "vs30" in header:
                        ind = header.index("vs30")
                        vs30s = []
                        for row in reader:
                            vs30s.append(int(row[ind]))

        backarc_flags = map(int, within_polygon(locations, backarc_polygon()))
        if any(self.model.hazard_config.get_uniform_site_params()):
            self.model.hazard_config.set_sites(locations, backarc=backarc_flags)
        else:
            self.model.hazard_config.set_sites(locations, vs30=vs30s, backarc=backarc_flags)

    def set_hazard_curve_parameters(self, task_arguments: Dict[str, Any]):
        """Set hazard curve for hazard curve calculation

        Args:
            task_arguments: a dict of task arguments
        """
        imts = task_arguments["hazard_curve"]["imts"]
        imtls = task_arguments["hazard_curve"]["imtls"]
        self.model.hazard_config.set_iml(imts, imtls)

    def set_disagg_matrix_parameters(self, task_arguments: Dict[str, Any]):
        """Set disagg matrix coordinates and point on hazard curve to disaggregate

        Args:
            task_arguments: a dict of task arguments
        """
        self.model.hazard_config.set_iml_disagg(
            imt=task_arguments["hazard_curve"]["imt"], level=task_arguments["disagg"]["target_level"]
        )
        self.model.hazard_config.set_parameter("general", "calculation_mode", "disaggregation")
        self.model.hazard_config.set_parameter(
            "disaggregation", "disagg_outputs", " ".join(task_arguments["disagg"]["disagg_outputs"])
        )
        if mag_bin_width := task_arguments["disagg"]["mag_bin_width"]:
            self.model.hazard_config.set_parameter("disaggregation", "mag_bin_width", mag_bin_width)
        if distance_bin_width := task_arguments["disagg"]["distance_bin_width"]:
            self.model.hazard_config.set_parameter("disaggregation", "distance_bin_width", distance_bin_width)
        if coordinate_bin_width := task_arguments["disagg"]["coordinate_bin_width"]:
            self.model.hazard_config.set_parameter("disaggregation", "coordinate_bin_width", coordinate_bin_width)
        if num_epsilon_bins := task_arguments["disagg"]["num_epsilon_bins"]:
            self.model.hazard_config.set_parameter("disaggregation", "num_epsilon_bins", num_epsilon_bins)
        if disagg_bin_edges := task_arguments["disagg"]["disagg_bin_edges"]:
            self.model.hazard_config.set_parameter("disaggregation", "disagg_bin_edges", disagg_bin_edges)

    @staticmethod
    def get_disagg_description(task_arguments: Dict[str, Any]):
        """get the description string for a disaggregation

        Args:
            task_arguments: a dict of task arguments
        """
        return (
            f"Disaggregation for site: {task_arguments['site_params']['locations'][0]}, "
            f"vs30: {task_arguments['site_params']['vs30']}, "
            f"IMT: {task_arguments['hazard_curve']['imt']}, "
            f"agg: {task_arguments['hazard_curve']['agg']}, "
            f"{task_arguments['disagg']['poe']} in {task_arguments['disagg']['inv_time']} years"
        )

    # TODO: we need to consider the best way to pass args to toshiAPI and make the args such as logic
    # trees and hazard config readable and (possibly) searchable.
    @staticmethod
    def _clean_task_args(task_arguments: Dict[str, Any]) -> Dict[str, str]:
        """This is a somewhat clunky way to clean the arguments so they can be passed to the toshAPI"""

        def flatten_dict(data, parent_key='', separator="-"):
            flat_dict = {}
            for k, v in data.items():
                key = parent_key + separator + k if parent_key else k
                if isinstance(v, dict):
                    flat_dict.update(flatten_dict(v, key))
                else:
                    flat_dict[key] = v
            return flat_dict

        def clean_string(input_str):
            return input_str.replace('"', "``").replace("\n", "-")

        ta_clean = copy.deepcopy(task_arguments)
        ta_clean["hazard_model"]["srm_logic_tree"] = clean_string(str(ta_clean["hazard_model"]["srm_logic_tree"]))
        ta_clean["hazard_model"]["gmcm_logic_tree"] = clean_string(str(ta_clean["hazard_model"]["gmcm_logic_tree"]))
        ta_clean["hazard_model"]["hazard_config"] = clean_string(str(ta_clean["hazard_model"]["hazard_config"]))
        return flatten_dict(ta_clean)

    def run(self, task_arguments: Dict[str, Any], job_arguments: Dict[str, Any]):
        t0 = dt.datetime.now(dt.timezone.utc)
        task_arguments, job_arguments
        environment = {
            "host": platform.node(),
            "openquake.version": "SPOOFED" if SPOOF_HAZARD else "TODO: get openquake version",
        }

        try:
            task_type = HazardTaskType[task_arguments["task_type"]]
        except KeyError:
            raise ValueError("Invalid configuration.")
        print(task_type)

        # convert the dict representations of complex objects (from nzshm_model lib) in the args to the correct type
        task_arguments["hazard_model"]["srm_logic_tree"] = SourceLogicTree.from_dict(
            task_arguments["hazard_model"]["srm_logic_tree"]
        )
        task_arguments["hazard_model"]["gmcm_logic_tree"] = GMCMLogicTree.from_dict(
            task_arguments["hazard_model"]["gmcm_logic_tree"]
        )
        task_arguments["hazard_model"]["hazard_config"] = OpenquakeConfig.from_dict(
            task_arguments["hazard_model"]["hazard_config"]
        )

        ################
        # API SETUP
        ################
        automation_task_id = None
        if self.use_api:
            # old config id until we've removed need for config_id when creating task
            # config_id = "T3BlbnF1YWtlSGF6YXJkQ29uZmlnOjEyOTI0NA=="  # PROD
            config_id = "T3BlbnF1YWtlSGF6YXJkQ29uZmlnOjEwMTU3MA=="  # TEST
            ta_clean = self._clean_task_args(task_arguments)
            automation_task_id = self._setup_automation_task(ta_clean, job_arguments, config_id, environment, task_type)

        #################################
        # SETUP openquake CONFIG FOLDER
        #################################
        work_folder = Path(WORK_PATH)
        task_no = job_arguments["task_id"]
        config_folder = work_folder / f"config_{task_no}"

        self.model = NshmModel(
            version="",
            title=task_arguments["general"]["title"],
            source_logic_tree=task_arguments["hazard_model"]["srm_logic_tree"],
            gmcm_logic_tree=task_arguments["hazard_model"]["gmcm_logic_tree"],
            hazard_config=task_arguments["hazard_model"]["hazard_config"],
        )

        # set sites and site parameters
        self.set_site_parameters(task_arguments)

        # set description, hazard curve, and disaggregation matrix parameters
        if HazardTaskType[task_arguments["task_type"]] is HazardTaskType.HAZARD:
            self.set_hazard_curve_parameters(task_arguments)
            description = task_arguments["general"]["description"]
        elif HazardTaskType[task_arguments["task_type"]] is HazardTaskType.DISAGG:
            self.set_disagg_matrix_parameters(task_arguments)
            description = self.get_disagg_description(task_arguments)

        self.model.hazard_config.set_description(description)

        cache_folder = config_folder / "downloads"
        job_file = self.model.psha_adapter(OpenquakeModelPshaAdapter).write_config(cache_folder, config_folder)

        ##############
        # EXECUTE
        ##############
        oq_result = execute_openquake(
            job_file,
            job_arguments["task_id"],
            automation_task_id,
            HazardTaskType[task_arguments["task_type"]],
        )

        ######################
        # API STORE RESULTS #
        ######################
        if self.use_api:
            solution_id = self._store_api_result(
                automation_task_id,
                ta_clean,
                oq_result,
                config_id,
                modconf_id=config_id,  # TODO use modified config id
                duration=(dt.datetime.now(dt.timezone.utc) - t0).total_seconds(),
            )

            #############################
            # STORE HAZARD REALIZATIONS #
            #############################
            # run the store_hazard job
            if not SPOOF_HAZARD and (not oq_result.get("no_ruptures")):
                # [{'tag': 'GRANULAR', 'weight': 1.0, 'permute': [{'group': 'ALL', 'members': [ltb._asdict()] }]}]
                # TODO GRANULAR ONLY@!@
                # ltb = {"tag": "hiktlck, b0.979, C3.9, s0.78", "weight": 0.0666666666666667,
                #        "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwODA3NQ==", "bg_id":"RmlsZToxMDY1MjU="},

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
                source_logic_tree = task_arguments["hazard_model"]["srm_logic_tree"]
                tag = ":".join(
                    (
                        source_logic_tree.branch_sets[0].short_name,
                        source_logic_tree.branch_sets[0].branches[0].tag,
                    )
                )
                locations = (
                    task_arguments["site_params"].get("locations")
                    or task_arguments["site_params"].get("locations_file_id")
                    or task_arguments["site_params"]["locations_file"]
                )
                source_ids = ", ".join([b.nrml_id for b in source_logic_tree.fault_systems[0].branches[0].sources])
                cmd = [
                    "store_hazard_v3",
                    str(oq_result["oq_calc_id"]),
                    solution_id,
                    job_arguments["general_task_id"],
                    str(locations),
                    f'"{tag}"',
                    f'"{source_ids}"',
                    "--verbose",
                    "--create-tables",
                ]
                # THS does not yet support storing disaggregation realizations
                if HazardTaskType[task_arguments["task_type"]] is HazardTaskType.DISAGG:
                    cmd.append("--meta-data-only")
                log.info(f"store_hazard: {cmd}")
                subprocess.check_call(cmd)

        t1 = dt.datetime.now(dt.timezone.utc)
        log.info("Task took %s secs" % (t1 - t0).total_seconds())


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
        f = open(args.config, "r", encoding="utf-8")
        config = json.load(f)
    except Exception:
        # for AWS this must now be a compressed JSON string
        config = json.loads(decompress_config(args.config))

    sleep_multiplier = config["job_arguments"].get("sleep_multiplier", 2)
    sleep_multiplier = sleep_multiplier if sleep_multiplier else 2
    time.sleep(int(config["job_arguments"]["task_id"]) * sleep_multiplier)
    task = BuilderTask(config["job_arguments"])
    task.run(**config)
