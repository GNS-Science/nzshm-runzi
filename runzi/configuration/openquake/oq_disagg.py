import copy
import csv
import getpass
import itertools
import json
import os
import stat
from collections import namedtuple
from pathlib import PurePath
from typing import TYPE_CHECKING, Generator

import numpy as np
import toshi_hazard_store
from nzshm_common.location import get_locations
from nzshm_model import get_model_version
from nzshm_model.logic_tree import GMCMLogicTree, SourceLogicTree
from nzshm_model.psha_adapter.openquake import OpenquakeConfig

import runzi.execute.openquake.oq_hazard_task
from runzi.automation.scaling.local_config import (
    API_KEY,
    API_URL,
    CLUSTER_MODE,
    S3_REPORT_BUCKET,
    S3_URL,
    USE_API,
    WORK_PATH,
    EnvMode,
)
from runzi.automation.scaling.python_task_factory import get_factory
from runzi.automation.scaling.toshi_api import CreateGeneralTaskArgs, ModelType, SubtaskType, ToshiApi
from runzi.automation.scaling.toshi_api.openquake_hazard.openquake_hazard_task import HazardTaskType
from runzi.util.aws import BatchEnvironmentSetting, get_ecs_job_config

from .util import EC2_CONFIGS, ComputePlatform

if TYPE_CHECKING:
    from toshi_hazard_store.model import AggregationEnum

    from runzi.automation.openquake.config import DisaggConfig


HAZARD_MAX_TIME = 20  # minutes

COMPUTE_PLATFORM = ComputePlatform.EC2
EC2_CONFIG = EC2_CONFIGS["BL_CONF_2"]  # BL_CONF_32_120

factory_class = get_factory(CLUSTER_MODE)
factory_task = runzi.execute.openquake.oq_hazard_task
task_factory = factory_class(WORK_PATH, factory_task, task_config_path=WORK_PATH)

GT_COUNTER = 0


def compute_hazard_at_poe(levels: list[float], values: list[float], poe: float, inv_time: float):
    rp = -inv_time / np.log(1 - poe)
    haz = np.exp(np.interp(np.log(1 / rp), np.flip(np.log(values)), np.flip(np.log(levels))))
    return haz


def get_target_level(
    hazard_model_id: str,
    location: str,
    vs30: int,
    imt: str,
    agg: 'AggregationEnum',
    poe: float,
    inv_time: float,
):

    hc = next(toshi_hazard_store.query_v3.get_hazard_curves([location], [vs30], [hazard_model_id], [imt], [agg.value]))
    levels = []
    hazard_vals = []
    for v in hc.values:
        levels.append(float(v.lvl))
        hazard_vals.append(float(v.val))

    return compute_hazard_at_poe(levels, hazard_vals, poe, inv_time)


def build_task(task_arguments, job_arguments, task_id, extra_env):

    if CLUSTER_MODE == EnvMode['AWS']:
        job_name = f"Runzi-automation-oq-disagg-{task_id}"
        config_data = dict(task_arguments=task_arguments, job_arguments=job_arguments)

        if COMPUTE_PLATFORM is ComputePlatform.EC2:
            return get_ecs_job_config(
                job_name,
                'N/A',
                config_data,
                toshi_api_url=API_URL,
                toshi_s3_url=S3_URL,
                toshi_report_bucket=S3_REPORT_BUCKET,
                task_module=runzi.execute.openquake.oq_hazard_task.__name__,
                time_minutes=int(HAZARD_MAX_TIME),
                memory=EC2_CONFIG["mem"],
                vcpu=EC2_CONFIG["cpu"],
                job_definition=EC2_CONFIG["job_def"],  # "BigLeverOnDemandEC2-JD", # "BiggerLever-runzi-openquake-JD",
                job_queue=EC2_CONFIG["job_queue"],
                extra_env=extra_env,
                use_compression=True,
            )
        elif COMPUTE_PLATFORM is ComputePlatform.Fargate:
            return get_ecs_job_config(
                job_name,
                'N/A',
                config_data,
                toshi_api_url=API_URL,
                toshi_s3_url=S3_URL,
                toshi_report_bucket=S3_REPORT_BUCKET,
                task_module=runzi.execute.openquake.oq_hazard_task.__name__,
                time_minutes=int(HAZARD_MAX_TIME),
                memory=30720,
                vcpu=4,
                job_definition="Fargate-runzi-openquake-JD",
                extra_env=extra_env,
                use_compression=True,
            )
    else:
        # write a config
        task_factory.write_task_config(task_arguments, job_arguments)
        script, task_number = task_factory.get_task_script()

        script_file_path = PurePath(WORK_PATH, f"task_{task_number}.sh")
        with open(script_file_path, 'w') as f:
            f.write(script)

        # make file executable
        st = os.stat(script_file_path)
        os.chmod(script_file_path, st.st_mode | stat.S_IEXEC)

        return str(script_file_path)


def new_general_task(gt_arguments, title, description, subtask_type, model_type):

    if not USE_API:
        global GT_COUNTER
        GT_COUNTER += 1
        return f'none_{GT_COUNTER}'

    headers = {"x-api-key": API_KEY}
    toshi_api = ToshiApi(API_URL, None, None, with_schema_validation=True, headers=headers)

    args_list = []
    for key, value in gt_arguments.items():
        args_list.append(dict(k=key, v=str(value)))

    if USE_API:

        # create new task in toshi_api
        gt_args = (
            CreateGeneralTaskArgs(
                agent_name=getpass.getuser(),
                title=title,
                description=description,
            )
            .set_argument_list(args_list)
            .set_subtask_type(subtask_type)
            .set_model_type(model_type)
        )

        gt_id = toshi_api.general_task.create_task(gt_args)

    return gt_id


LocVs30 = namedtuple("LocVs30", ["loc", "vs30"])


def get_loc_vs30(job_config: 'DisaggConfig') -> Generator[LocVs30, None, None]:
    if job_config.site_params.locations:
        locations = get_locations(job_config.site_params.locations)
    else:
        locations = get_locations([job_config.site_params.locations_file])
    vs30s = job_config.site_params.vs30s
    if vs30s:
        for loc, vs30 in itertools.product(locations, vs30s):
            yield LocVs30(loc=loc.code, vs30=vs30)
    else:
        if job_config.site_params.locations_file is None:
            raise TypeError("locations_file not specified")
        with job_config.site_params.locations_file.open() as lf:
            reader = csv.reader(lf)
            header = next(reader)
            col_vs30 = header.index("vs30")
            for i, row in enumerate(reader):
                yield LocVs30(loc=locations[i].code, vs30=int(row[col_vs30]))


def build_disagg_tasks(subtask_type: SubtaskType, model_type: ModelType, disagg_config: 'DisaggConfig'):
    task_count = 0

    extra_env = [
        BatchEnvironmentSetting(name="NZSHM22_HAZARD_STORE_STAGE", value="PROD"),
        BatchEnvironmentSetting(name="NZSHM22_HAZARD_STORE_REGION", value="ap-southeast-2"),
        BatchEnvironmentSetting(name="NZSHM22_HAZARD_STORE_NUM_WORKERS", value="1"),
    ]

    # some objects in the config (Path type) are not json serializable so we dump to json using the pydantic method
    # which handles these types and load back to json to clean it up so it can be passed to the toshi API
    if model_version := disagg_config.hazard_model.nshm_model_version:
        model = get_model_version(model_version)
        source_logic_tree = model.source_logic_tree
        gmcm_logic_tree = model.gmm_logic_tree
        hazard_config = model.hazard_config

    if gmcm_lt_fp := disagg_config.hazard_model.gmcm_logic_tree:
        gmcm_logic_tree = GMCMLogicTree.from_json(gmcm_lt_fp)
    if srm_lt_fp := disagg_config.hazard_model.srm_logic_tree:
        source_logic_tree = SourceLogicTree.from_json(srm_lt_fp)
    if hc_lt_fp := disagg_config.hazard_model.hazard_config:
        hazard_config = OpenquakeConfig.from_json(hc_lt_fp)

    task_arguments = json.loads(disagg_config.model_dump_json())
    for loc_vs30, poe, imt, agg in itertools.product(
        get_loc_vs30(disagg_config),  # create vs30 location pairs for iterating (this is to handle site-specific vs30)
        disagg_config.disagg.poes,
        disagg_config.hazard_curve.imts,
        disagg_config.hazard_curve.aggs,
    ):
        target_level = get_target_level(
            disagg_config.hazard_curve.hazard_model_id,
            loc_vs30.loc,
            loc_vs30.vs30,
            imt,
            agg,
            poe,
            disagg_config.disagg.inv_time,
        )

        ta = copy.copy(task_arguments)
        ta["hazard_model"]["gmcm_logic_tree"] = gmcm_logic_tree.to_dict()
        ta["hazard_model"]["hazard_config"] = hazard_config.to_dict()
        ta["site_params"]["locations"] = [loc_vs30.loc]
        ta["site_params"]["vs30"] = loc_vs30.vs30
        ta["disagg"]["poe"] = poe
        ta["disagg"]["target_level"] = target_level
        ta["hazard_curve"]["imt"] = imt
        ta["hazard_curve"]["agg"] = agg.value

        ta['task_type'] = HazardTaskType.DISAGG.name
        ta['model_type'] = model_type.name

        print('')
        print('task arguments MERGED')
        print('==========================')
        print(ta)
        print('==========================')
        print('')

        # This is done at the config level only because we use the GT to keep track a a single disaggegation (for
        # all logic tree brances). This would normally live at the run level
        gt_id = new_general_task(
            ta,
            disagg_config.general.title,
            disagg_config.general.description,
            subtask_type,
            model_type,
        )

        # iterate over every branch of the logic tree to create a task
        task_count = 0
        for branch in source_logic_tree:
            branch.weight = 1.0
            slt = SourceLogicTree.from_branches([branch])

            task_count += 1
            job_arguments = dict(
                task_id=task_count,
                general_task_id=gt_id,
                use_api=USE_API,
                sleep_multiplier=disagg_config.calculation.sleep_multiplier,
            )
            ta['hazard_model']['srm_logic_tree'] = slt.to_dict()
            yield build_task(ta, job_arguments, task_count, extra_env), gt_id
