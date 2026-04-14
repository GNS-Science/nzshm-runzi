"""Openquake Hazard Task."""

import datetime as dt
import json
import logging
import platform
import time
from pathlib import Path
from typing import TYPE_CHECKING

from dateutil.tz import tzutc
from nshm_toshi_client.task_relation import TaskRelation
from nzshm_common.geometry.geometry import backarc_polygon, within_polygon
from nzshm_common.location.location import get_locations
from nzshm_hazlab.base_functions import calculate_hazard_at_poe, convert_poe
from nzshm_hazlab.data.data_loaders import THSHazardLoader
from nzshm_hazlab.data.hazard_curves import HazardCurves
from nzshm_model import NshmModel
from nzshm_model.logic_tree import GMCMLogicTree, SourceLogicTree
from nzshm_model.psha_adapter.openquake import OpenquakeModelPshaAdapter
from nzshm_model.psha_adapter.openquake.hazard_config import OpenquakeConfig

from runzi.arguments import SystemArgs, TaskLanguage
from runzi.automation.local_config import API_KEY, API_URL, ECR_DIGEST, S3_URL, SPOOF, THS_RLZ_DB, USE_API, WORK_PATH
from runzi.automation.toshi_api import ModelType, ToshiApi
from runzi.automation.toshi_api.openquake_hazard.openquake_hazard_task import HazardTaskType
from runzi.tasks.get_config import get_config
from runzi.tasks.oq_hazard.execute_openquake import execute_openquake
from runzi.tasks.oq_hazard.hazard_args import OQDisaggArgs

if TYPE_CHECKING:
    from toshi_hazard_store.model import AggregationEnum

# logging.basicConfig(level=logging.DEBUG)

LOG_INFO = logging.INFO
logging.getLogger("py4j.java_gateway").setLevel(LOG_INFO)
logging.getLogger("nshm_toshi_client.toshi_client_base").setLevel(LOG_INFO)
logging.getLogger("nshm_toshi_client.toshi_file").setLevel(LOG_INFO)
logging.getLogger("urllib3").setLevel(LOG_INFO)
logging.getLogger("botocore").setLevel(LOG_INFO)
logging.getLogger("git.cmd").setLevel(LOG_INFO)
logging.getLogger("gql.transport").setLevel(logging.WARN)

log = logging.getLogger(__name__)

try:
    from toshi_hazard_store.scripts.ths_rlz_import import store_hazard
except ModuleNotFoundError:
    log.info("not importing from toshi_hazard_store.scripts.ths_import due to missing dependencies")

default_system_args = SystemArgs(
    task_language=TaskLanguage.PYTHON,
    use_api=USE_API,
    ecs_max_job_time_min=30,
    ecs_memory=30000,
    ecs_vcpu=8,
    ecs_job_definition="BigLever_32GB_8VCPU_v2_JD",
    ecs_job_queue="BigLever_32GB_8VCPU_v2_JQ",
)


def get_target_level(
    hazard_model_id: str,
    location: str,
    vs30: int,
    imt: str,
    agg: 'AggregationEnum',
    poe: float,
    inv_time: float,
) -> float:
    loader = THSHazardLoader()
    hazard_curves = HazardCurves(loader=loader)
    imtl, apoe = hazard_curves.get_hazard_curve(hazard_model_id, imt, location, vs30, agg.value)
    poe = convert_poe(poe, inv_time_in=inv_time, inv_time_out=1.0)
    return calculate_hazard_at_poe(poe, imtl, apoe)


class OQDisaggTask:
    def __init__(self, user_args: OQDisaggArgs, system_args: SystemArgs):
        self.use_api = system_args.use_api
        self.user_args = user_args
        self.system_args = system_args

        if self.use_api:
            headers = {"x-api-key": API_KEY}
            self._toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
            self._task_relation_api = TaskRelation(API_URL, None, with_schema_validation=True, headers=headers)

    def set_disaggregation_params(self):
        self.model.hazard_config.set_parameter("general", "calculation_mode", "disaggregation")
        self.model.hazard_config.set_parameter(
            "disaggregation", "disagg_outputs", " ".join(self.user_args.disagg_types)
        )
        if mag_bin_width := self.user_args.mag_bin_width:
            self.model.hazard_config.set_parameter("disaggregation", "mag_bin_width", mag_bin_width)
        if distance_bin_width := self.user_args.distance_bin_width:
            self.model.hazard_config.set_parameter("disaggregation", "distance_bin_width", distance_bin_width)
        if coordinate_bin_width := self.user_args.coordinate_bin_width:
            self.model.hazard_config.set_parameter("disaggregation", "coordinate_bin_width", coordinate_bin_width)
        if num_epsilon_bins := self.user_args.num_epsilon_bins:
            self.model.hazard_config.set_parameter("disaggregation", "num_epsilon_bins", num_epsilon_bins)
        if disagg_bin_edges := self.user_args.disagg_bin_edges:
            self.model.hazard_config.set_parameter("disaggregation", "disagg_bin_edges", disagg_bin_edges)

        location = get_locations(self.user_args.locations)[0]
        target_imtl = get_target_level(
            self.user_args.hazard_model_id,
            location,
            self.user_args.vs30,
            self.user_args.imt,
            self.user_args.agg,
            self.user_args.poe,
            self.user_args.investigation_time,
        )
        self.model.hazard_config.set_iml_disagg(imt=self.user_args.imt, level=target_imtl)

    def _setup_automation_task(self) -> str:

        model_type = ModelType.COMPOSITE
        environment = {
            "host": platform.node(),
            "openquake.version": "SPOOFED" if SPOOF else "TODO: get openquake version",
        }

        srm_logic_tree: SourceLogicTree = self.user_args.srm_logic_tree
        gmcm_logic_tree: GMCMLogicTree = self.user_args.gmcm_logic_tree
        openquake_config: OpenquakeConfig = self.user_args.hazard_config

        automation_task_id = self._toshi_api.openquake_hazard_task.create_task(
            dict(
                created=dt.datetime.now(tzutc()).isoformat(),
                model_type=model_type.name.upper(),
                srm_logic_tree=json.dumps(srm_logic_tree.to_dict()),
                gmcm_logic_tree=json.dumps(gmcm_logic_tree.to_dict()),
                openquake_config=json.dumps(openquake_config.to_dict()),
            ),
            arguments=self.user_args.model_dump(
                mode='json', exclude={'hazard_model', 'srm_logic_tree', 'gmcm_logic_tree', 'hazard_config'}
            ),
            # arguments={"a": 1},
            environment=environment,
            task_type=HazardTaskType.HAZARD,
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
                meta=self.user_args.model_dump(
                    mode='json', exclude={'hazard_model', 'srm_logic_tree', 'gmcm_logic_tree', 'hazard_config'}
                ),
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
        location = self.user_args.site.location
        vs30 = self.user_args.site.vs30
        self.model.hazard_config.set_uniform_site_params(vs30)
        backarc_flags = map(int, within_polygon([location], backarc_polygon()))
        self.model.hazard_config.set_sites([location], backarc=backarc_flags)

    def run(self):
        t0 = dt.datetime.now(dt.timezone.utc)

        if self.user_args.srm_logic_tree is None:
            raise ValueError("SRM logic tree or path to file not provided")
        else:
            if isinstance(self.user_args.srm_logic_tree, Path):
                source_logic_tree = SourceLogicTree.from_json(self.user_args.srm_logic_tree)
            else:
                source_logic_tree = self.user_args.srm_logic_tree

        if self.user_args.gmcm_logic_tree is None:
            raise ValueError("GMCM logic tree or path to file not provided")
        else:
            if isinstance(self.user_args.gmcm_logic_tree, Path):
                gmcm_logic_tree = GMCMLogicTree.from_json(self.user_args.gmcm_logic_tree)
            else:
                gmcm_logic_tree = self.user_args.gmcm_logic_tree

        if self.user_args.hazard_config is None:
            raise ValueError("GMCM logic tree or path to file not provided")
        else:
            if isinstance(self.user_args.hazard_config, Path):
                hazard_config = OpenquakeConfig.from_json(self.user_args.hazard_config)
            else:
                hazard_config = self.user_args.hazard_config

        ################
        # API SETUP
        ################
        automation_task_id = None
        if self.use_api:
            automation_task_id = self._setup_automation_task()

        #################################
        # SETUP openquake CONFIG FOLDER
        #################################
        work_folder = WORK_PATH
        task_no = self.system_args.task_count
        config_folder = work_folder / f"config_{task_no}"

        description = f"disaggregation task: {task_no}"
        self.model = NshmModel(
            version="",
            title=description,
            source_logic_tree=source_logic_tree,
            gmcm_logic_tree=gmcm_logic_tree,
            hazard_config=hazard_config,
        )
        self.model.hazard_config.set_description(description)

        self.set_disaggregation_params()
        self.set_site_parameters()
        cache_folder = config_folder / "downloads"
        job_file = self.model.psha_adapter(OpenquakeModelPshaAdapter).write_config(cache_folder, config_folder)

        ##############
        # EXECUTE
        ##############
        oq_result = execute_openquake(
            job_file,
            self.system_args.task_count,
            automation_task_id,
            HazardTaskType.HAZARD,
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
                    self.user_args.compatible_calc_id,
                    solution_id,
                    ECR_DIGEST,
                    THS_RLZ_DB,
                )

        t1 = dt.datetime.now(dt.timezone.utc)
        log.info("Task took %s secs" % (t1 - t0).total_seconds())


if __name__ == "__main__":
    config = get_config()

    # print(config)
    user_args = OQDisaggArgs(**config['task_args'])
    system_args = SystemArgs(**config['task_system_args'])
    task = OQDisaggTask(user_args, system_args)

    # Wait for some more time, scaled by taskid to avoid S3 consistency issue
    time.sleep(system_args.task_count)

    task.run()
