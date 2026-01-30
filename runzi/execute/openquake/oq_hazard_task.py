"""Openquake Hazard Task."""

import argparse
import copy
import csv
import datetime as dt
import json
import logging
import platform
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
from nzshm_model.psha_adapter.openquake import OpenquakeModelPshaAdapter
from nzshm_model.psha_adapter.openquake.hazard_config import OpenquakeConfig

from runzi.automation.scaling.local_config import API_KEY, API_URL, ECR_DIGEST, S3_URL, SPOOF, THS_RLZ_DB, WORK_PATH
from runzi.automation.scaling.toshi_api import ModelType, ToshiApi
from runzi.automation.scaling.toshi_api.openquake_hazard.openquake_hazard_task import HazardTaskType
from runzi.execute.arguments import SystemArgs
from runzi.execute.openquake.execute_openquake import execute_openquake
from runzi.runners import DisaggInput, HazardInput
from runzi.runners.hazard_inputs import HazardInputBase
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

try:
    from toshi_hazard_store.scripts.ths_import import store_hazard
except ModuleNotFoundError:
    log.info("not importing from toshi_hazard_store.scripts.ths_import due to missing dependencies")


class BuilderTask:
    def __init__(self, user_args: HazardInput | DisaggInput, system_args: SystemArgs):
        self.use_api = system_args.use_api
        self.user_args = user_args
        self.system_args = system_args

        if self.use_api:
            headers = {"x-api-key": API_KEY}
            self._toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
            self._task_relation_api = TaskRelation(API_URL, None, with_schema_validation=True, headers=headers)

    def _setup_automation_task(self) -> str:

        model_type = ModelType.COMPOSITE
        environment = {
            "host": platform.node(),
            "openquake.version": "SPOOFED" if SPOOF else "TODO: get openquake version",
        }

        srm_logic_tree: SourceLogicTree = self.user_args.hazard_model.srm_logic_tree
        gmcm_logic_tree: GMCMLogicTree = self.user_args.hazard_model.gmcm_logic_tree
        openquake_config: OpenquakeConfig = self.user_args.hazard_model.hazard_config

        automation_task_id = self._toshi_api.openquake_hazard_task.create_task(
            dict(
                created=dt.datetime.now(tzutc()).isoformat(),
                model_type=model_type.name.upper(),
                srm_logic_tree=json.dumps(srm_logic_tree.to_dict()),
                gmcm_logic_tree=json.dumps(gmcm_logic_tree.to_dict()),
                openquake_config=json.dumps(openquake_config.to_dict()),
            ),
            arguments=self.user_args.model_dump(mode='json', exclude={'hazard_model'}),
            environment=environment,
            task_type=self.user_args.task_type,
        )

        # link OpenquakeHazardTask to the parent GT
        gt_conn = self._task_relation_api.create_task_relation(self.system_args.general_task_id, automation_task_id)
        print(
            f"created task_relationship: {gt_conn} "
            f"for at: {automation_task_id} "
            f"on GT: {self.system_args.general_task_id}"
        )

        return automation_task_id

    def _store_api_result(
        self,
        automation_task_id,
        oq_result,
        duration,
    ):
        """Record results in API."""

        # make a json file from the ta dict so we can save it.
        json_filepath = Path(WORK_PATH, "task_args.json")
        json_filepath.write_text(self.user_args.model_dump_json(indent=2))

        # save the json
        task_args_id, post_url = self._toshi_api.file.create_file(json_filepath)
        self._toshi_api.file.upload_content(post_url, json_filepath)
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
                csv_archive_id,
                hdf5_archive_id,
                produced_by=automation_task_id,
                predecessors=predecessors,
                task_args_id=task_args_id,
                meta=self.user_args.model_dump(mode='json', exclude={'hazard_model'}),
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
                executor="ECRD:" + ECR_DIGEST,
            ),
            metrics=metrics,
        )

        return solution_id

    def set_site_parameters(self):
        """Set site locations and vs30s for the NshmModel"""
        if self.user_args.site_params.vs30s:
            # TODO: this is the same shit swept arg pattern used elsewhere that we will fix, but may
            # be harder for hazard jobs
            vs30 = self.user_args.site_params.vs30s[0]
            self.model.hazard_config.set_uniform_site_params(vs30)

        # if task_arguments["site_params"].get("locations"):
        if self.user_args.site_params.locations:
            locations = get_locations(self.user_args.site_params.locations)
        else:
            with tempfile.TemporaryDirectory() as temp_dir:
                if file_id := self.user_args.site_params.locations_file_id:
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
                    locations_file = self.user_args.site_params.locations_file
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
        ta_clean["hazard_model"]["srm_logic_tree"] = json.dumps(ta_clean["hazard_model"]["srm_logic_tree"])
        ta_clean["hazard_model"]["gmcm_logic_tree"] = json.dumps(ta_clean["hazard_model"]["gmcm_logic_tree"])
        ta_clean["hazard_model"]["hazard_config"] = json.dumps(ta_clean["hazard_model"]["hazard_config"])
        return flatten_dict(ta_clean)

    def run(self):
        t0 = dt.datetime.now(dt.timezone.utc)

        source_logic_tree = self.user_args.hazard_model.srm_logic_tree
        gmcm_logic_tree = self.user_args.hazard_model.gmcm_logic_tree
        hazard_config = self.user_args.hazard_model.hazard_config

        ################
        # API SETUP
        ################
        automation_task_id = None
        if self.use_api:
            automation_task_id = self._setup_automation_task()

        #################################
        # SETUP openquake CONFIG FOLDER
        #################################
        work_folder = Path(WORK_PATH)
        task_no = self.system_args.task_count
        config_folder = work_folder / f"config_{task_no}"

        self.model = NshmModel(
            version="",
            title=self.user_args.general.title,
            source_logic_tree=source_logic_tree,
            gmcm_logic_tree=gmcm_logic_tree,
            hazard_config=hazard_config,
        )
        self.model.hazard_config.set_description(self.user_args.general.description)

        # set sites and site parameters
        self.set_site_parameters()

        # set description, hazard curve, and disaggregation matrix parameters
        # need user args to include task type
        if self.user_args.task_type is HazardTaskType.HAZARD:
            self.model.hazard_config.set_iml(self.user_args.hazard_curve.imts, self.user_args.hazard_curve.imtls)
        elif self.user_args.task_type is HazardTaskType.DISAGG:
            pass
            # self.set_disagg_matrix_parameters(task_arguments)
            # description = self.get_disagg_description(task_arguments)

        cache_folder = config_folder / "downloads"
        job_file = self.model.psha_adapter(OpenquakeModelPshaAdapter).write_config(cache_folder, config_folder)

        ##############
        # EXECUTE
        ##############
        oq_result = execute_openquake(
            job_file,
            self.system_args.task_count,
            automation_task_id,
            self.user_args.task_type,
        )

        ######################
        # API STORE RESULTS #
        ######################
        if self.use_api:
            solution_id = self._store_api_result(
                automation_task_id,
                oq_result,
                duration=(dt.datetime.now(dt.timezone.utc) - t0).total_seconds(),
            )

            #############################
            # STORE HAZARD REALIZATIONS #
            #############################
            # run the store_hazard job
            if not SPOOF and (not oq_result.get("no_ruptures")):

                # write config to json
                config_filepath = config_folder / "hazard_config.json"
                hazard_config.to_json(config_filepath)

                # # THS does not yet support storing disaggregation realizations
                log.info("store hazard")
                store_hazard(
                    str(oq_result["hdf5_filepath"]),
                    config_filepath,
                    self.user_args.general.compatible_calc_id,
                    solution_id,
                    ECR_DIGEST,
                    THS_RLZ_DB,
                )

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

    user_args: HazardInputBase
    if HazardTaskType(config['task_args']['task_type']) is HazardTaskType.HAZARD:
        user_args = HazardInput(**config['task_args'])
    elif HazardTaskType(config['task_args']['task_type']) is HazardTaskType.DISAGG:
        user_args = DisaggInput(**config['task_args'])
    else:
        raise ValueError("task type must be HAZARD or DISAGG")

    system_args = SystemArgs(**config['task_system_args'])

    sleep_multiplier = 2.0
    time.sleep(system_args.task_count * sleep_multiplier)
    task = BuilderTask(user_args, system_args)
    task.run()
