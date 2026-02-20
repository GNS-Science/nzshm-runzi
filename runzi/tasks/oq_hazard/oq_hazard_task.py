"""Openquake Hazard Task."""

import argparse
import csv
import datetime as dt
import json
import logging
import platform
import tempfile
import time
import urllib
from pathlib import Path

from dateutil.tz import tzutc
from nshm_toshi_client import ToshiFile
from nshm_toshi_client.task_relation import TaskRelation
from nzshm_common.geometry.geometry import backarc_polygon, within_polygon
from nzshm_common.location import CodedLocation, get_locations
from nzshm_model import NshmModel
from nzshm_model.logic_tree import GMCMLogicTree, SourceLogicTree
from nzshm_model.psha_adapter.openquake import OpenquakeModelPshaAdapter
from nzshm_model.psha_adapter.openquake.hazard_config import OpenquakeConfig

from runzi.automation.scaling.local_config import (
    API_KEY,
    API_URL,
    ECR_DIGEST,
    S3_URL,
    SPOOF,
    THS_RLZ_DB,
    USE_API,
    WORK_PATH,
)
from runzi.automation.scaling.toshi_api import ModelType, ToshiApi
from runzi.automation.scaling.toshi_api.openquake_hazard.openquake_hazard_task import HazardTaskType
from runzi.arguments import SystemArgs, TaskLanguage
from runzi.tasks.oq_hazard.execute_openquake import execute_openquake
from runzi.tasks.oq_hazard.hazard_args import OQHazardArgs

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

default_system_args = SystemArgs(
    task_language=TaskLanguage.PYTHON,
    use_api=USE_API,
    ecs_max_job_time_min=30,
    ecs_memory=30000,
    ecs_vcpu=8,
    ecs_job_definition="BigLever_32GB_8VCPU_v2_JD",
    ecs_job_queue="BigLever_32GB_8VCPU_v2_JQ",
)


def get_locations_from_file(
    locations_file: Path | None, locations_file_id: str | None
) -> tuple[list[CodedLocation], list[int]]:
    if (locations_file_id is None) and (locations_file is None):
        raise ValueError("locations_file must not be None if locations_file_id is None")
    vs30s: list[int] = []
    with tempfile.TemporaryDirectory() as temp_dir:
        if locations_file_id:
            headers = {"x-api-key": API_KEY}
            file_api = ToshiFile(
                API_URL,
                None,
                None,
                with_schema_validation=True,
                headers=headers,
            )
            file_api.download_file(locations_file_id, target_dir=temp_dir, target_name="sites.csv")
            locations_file = Path(temp_dir) / "sites.csv"
        else:
            assert locations_file
            locations_file = locations_file
        locations = get_locations([locations_file])
        with locations_file.open() as lf:
            reader = csv.reader(lf)
            header = next(reader)
            if "vs30" in header:
                ind = header.index("vs30")
                for row in reader:
                    vs30s.append(int(row[ind]))
    return locations, vs30s


class OQHazardTask:
    def __init__(self, user_args: OQHazardArgs, system_args: SystemArgs):
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
        if self.user_args.locations:
            locations = get_locations(self.user_args.locations)
            vs30s = []
        else:
            locations, vs30s = get_locations_from_file(self.user_args.locations_file, self.user_args.locations_file_id)

        backarc_flags = map(int, within_polygon(locations, backarc_polygon()))
        if vs30s:
            self.model.hazard_config.set_sites(locations, vs30=vs30s, backarc=backarc_flags)
        else:
            assert self.user_args.vs30
            self.model.hazard_config.set_uniform_site_params(self.user_args.vs30)
            self.model.hazard_config.set_sites(locations, backarc=backarc_flags)

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

        description = f"hazard model for task: {task_no}"
        self.model = NshmModel(
            version="",
            title=description,
            source_logic_tree=source_logic_tree,
            gmcm_logic_tree=gmcm_logic_tree,
            hazard_config=hazard_config,
        )
        self.model.hazard_config.set_description(description)

        # set sites and site parameters
        self.set_site_parameters()

        self.model.hazard_config.set_iml(self.user_args.imts, self.user_args.imtls)

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

    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    args = parser.parse_args()

    try:
        # LOCAL and CLUSTER this is a file
        config_file = args.config
        f = open(args.config, 'r', encoding='utf-8')
        config = json.load(f)
    except FileNotFoundError:
        # for AWS this must be a quoted JSON string
        config = json.loads(urllib.parse.unquote(args.config))

    # print(config)
    user_args = OQHazardArgs(**config['task_args'])
    system_args = SystemArgs(**config['task_system_args'])
    task = OQHazardTask(user_args, system_args)

    # Wait for some more time, scaled by taskid to avoid S3 consistency issue
    time.sleep(system_args.task_count)

    task.run()
