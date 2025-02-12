import os
import stat
from pathlib import PurePath
from typing import Any, Dict, List, Optional

from nzshm_model import get_model_version
from nzshm_model.logic_tree import GMCMLogicTree, SourceLogicTree
from nzshm_model.psha_adapter.openquake.hazard_config import OpenquakeConfig

import runzi.execute.openquake.oq_hazard_task
from runzi.automation.scaling.local_config import (
    API_URL,
    CLUSTER_MODE,
    S3_REPORT_BUCKET,
    S3_URL,
    USE_API,
    WORK_PATH,
    EnvMode,
)
from runzi.automation.scaling.python_task_factory import get_factory
from runzi.automation.scaling.toshi_api import ModelType, SubtaskType
from runzi.automation.scaling.toshi_api.openquake_hazard.openquake_hazard_task import HazardTaskType
from runzi.util.aws import BatchEnvironmentSetting, get_ecs_job_config

from .util import EC2_CONFIGS, ComputePlatform

HAZARD_MAX_TIME = 48 * 60  # minutes

COMPUTE_PLATFORM = ComputePlatform.EC2
EC2_CONFIG = EC2_CONFIGS["BL_CONF_1"]  # BL_CONF_32_120

factory_class = get_factory(CLUSTER_MODE)
factory_task = runzi.execute.openquake.oq_hazard_task
task_factory = factory_class(WORK_PATH, factory_task, task_config_path=WORK_PATH)


def build_task(
    task_arguments: Dict[str, Any],
    job_arguments: Dict[str, Any],
    task_id: int,
    extra_env: Optional[List[BatchEnvironmentSetting]],
):
    if CLUSTER_MODE == EnvMode["AWS"]:
        job_name = f"Runzi-automation-oq-hazard-{task_id}"
        config_data = dict(task_arguments=task_arguments, job_arguments=job_arguments)

        if COMPUTE_PLATFORM is ComputePlatform.EC2:
            return get_ecs_job_config(
                job_name,
                "N/A",
                config_data,
                toshi_api_url=API_URL,
                toshi_s3_url=S3_URL,
                toshi_report_bucket=S3_REPORT_BUCKET,
                task_module=runzi.execute.openquake.oq_hazard_task.__name__,
                time_minutes=int(HAZARD_MAX_TIME),
                memory=EC2_CONFIG["mem"],
                vcpu=EC2_CONFIG["cpu"],
                job_definition=EC2_CONFIG["job_def"],
                job_queue=EC2_CONFIG["job_queue"],
                extra_env=extra_env,
                use_compression=True,
            )
        elif COMPUTE_PLATFORM is ComputePlatform.Fargate:
            return get_ecs_job_config(
                job_name,
                "N/A",
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

        script_file_path = PurePath(WORK_PATH, f"task_{task_id}.sh")
        with open(script_file_path, "w") as f:
            f.write(script)

        # make file executable
        st = os.stat(script_file_path)
        os.chmod(script_file_path, st.st_mode | stat.S_IEXEC)

        return str(script_file_path)


def build_hazard_tasks(
    general_task_id: str,
    subtask_type: SubtaskType,
    model_type: ModelType,
    task_args: Dict[str, Any],
):
    extra_env = [
        BatchEnvironmentSetting(name="NZSHM22_HAZARD_STORE_STAGE", value="PROD"),
        BatchEnvironmentSetting(name="NZSHM22_HAZARD_STORE_REGION", value="ap-southeast-2"),
        BatchEnvironmentSetting(name="NZSHM22_HAZARD_STORE_NUM_WORKERS", value="1"),
    ]

    task_count = 0

    if model_version := task_args["hazard_model"].get("nshm_model_version"):
        model = get_model_version(model_version)
        source_logic_tree = model.source_logic_tree
        gmcm_logic_tree = model.gmm_logic_tree
        hazard_config = model.hazard_config

    if gmcm_lt_fp := task_args["hazard_model"].get("gmcm_logic_tree"):
        gmcm_logic_tree = GMCMLogicTree.from_json(gmcm_lt_fp)
    if srm_lt_fp := task_args["hazard_model"].get("srm_logic_tree"):
        source_logic_tree = SourceLogicTree.from_json(srm_lt_fp)
    if hc_lt_fp := task_args["hazard_model"].get("hazard_config"):
        hazard_config = OpenquakeConfig.from_json(hc_lt_fp)

    task_args["hazard_model"]["gmcm_logic_tree"] = gmcm_logic_tree.to_dict()
    task_args["hazard_model"]["hazard_config"] = hazard_config.to_dict()

    task_args.update(
        dict(
            title=task_args["general"]["title"],
            description=task_args["general"]["description"],
            task_type=HazardTaskType.HAZARD.name,
            model_type=model_type.name,
        )
    )

    for branch in source_logic_tree:
        branch.weight = 1.0
        slt = SourceLogicTree.from_branches([branch])

        task_count += 1
        job_arguments = dict(
            task_id=task_count,
            general_task_id=general_task_id,
            use_api=USE_API,
            sleep_multiplier=task_args["calculation"].get("sleep_multiplier", 2),
        )
        task_args["hazard_model"]["srm_logic_tree"] = slt.to_dict()
        yield build_task(task_args, job_arguments, task_count, extra_env)
