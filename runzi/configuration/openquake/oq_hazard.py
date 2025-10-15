import os
import stat
from pathlib import PurePath

from nzshm_model import get_model_version
from nzshm_model.logic_tree import GMCMLogicTree, SourceLogicTree
from nzshm_model.psha_adapter.openquake.hazard_config import OpenquakeConfig

import runzi.execute.openquake.oq_hazard_task
from runzi.automation.scaling.local_config import (
    API_URL,
    CLUSTER_MODE,
    ECR_DIGEST,
    S3_REPORT_BUCKET,
    S3_URL,
    THS_RLZ_DB,
    WORK_PATH,
    EnvMode,
)
from runzi.automation.scaling.python_task_factory import get_factory
from runzi.runners import HazardInput
from runzi.runners.runner_inputs import SystemArgs
from runzi.util.aws import BatchEnvironmentSetting, get_ecs_job_config

from .util import EC2_CONFIGS, ComputePlatform

HAZARD_MAX_TIME = 48 * 60  # minutes

COMPUTE_PLATFORM = ComputePlatform.EC2
EC2_CONFIG = EC2_CONFIGS["BL_CONF_1"]  # BL_CONF_32_120

factory_class = get_factory(CLUSTER_MODE)
factory_task = runzi.execute.openquake.oq_hazard_task
task_factory = factory_class(WORK_PATH, factory_task, task_config_path=WORK_PATH)


def build_task(task_hazard_args: HazardInput, task_system_args: SystemArgs):

    extra_env = [
        BatchEnvironmentSetting(name="NZSHM22_RUNZI_ECR_DIGEST", value=ECR_DIGEST),
        BatchEnvironmentSetting(name="NZSHM22_THS_RLZ_DB", value=THS_RLZ_DB),
    ]

    if CLUSTER_MODE == EnvMode["AWS"]:
        job_name = f"Runzi-automation-oq-hazard-{task_system_args.task_count}"

        if COMPUTE_PLATFORM is ComputePlatform.EC2:
            return get_ecs_job_config(
                job_name,
                "N/A",
                task_hazard_args,
                task_system_args,
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
                task_hazard_args,
                task_system_args,
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
        task_factory.write_task_config(task_hazard_args, task_system_args)
        script, task_number = task_factory.get_task_script()

        script_file_path = PurePath(WORK_PATH, f"task_{task_system_args.task_count}.sh")
        with open(script_file_path, "w") as f:
            f.write(script)

        # make file executable
        st = os.stat(script_file_path)
        os.chmod(script_file_path, st.st_mode | stat.S_IEXEC)

        return str(script_file_path)


def build_hazard_tasks(hazard_args: HazardInput, system_args: SystemArgs):

    if model_version := hazard_args.hazard_model.nshm_model_version:
        model = get_model_version(model_version)
        source_logic_tree = model.source_logic_tree
        gmcm_logic_tree = model.gmm_logic_tree
        hazard_config = model.hazard_config

    if gmcm_lt_fp := hazard_args.hazard_model.gmcm_logic_tree:
        gmcm_logic_tree = GMCMLogicTree.from_json(gmcm_lt_fp)
    if srm_lt_fp := hazard_args.hazard_model.srm_logic_tree:
        source_logic_tree = SourceLogicTree.from_json(srm_lt_fp)
    if hc_lt_fp := hazard_args.hazard_model.hazard_config:
        hazard_config = OpenquakeConfig.from_json(hc_lt_fp)

    hazard_args.hazard_model.gmcm_logic_tree = gmcm_logic_tree
    hazard_args.hazard_model.hazard_config = hazard_config

    task_count = 0
    if hazard_args.site_params.vs30s:
        vs30s = hazard_args.site_params.vs30s
    else:
        vs30s = [0]  # placeholder to iterate over when vs30 not set
    for vs30 in vs30s:
        if vs30 != 0:
            task_vs30s = [vs30]
        else:
            task_vs30s = None
        for branch in source_logic_tree:
            task_count += 1

            task_system_args = system_args.model_copy(deep=True)
            task_hazard_args = hazard_args.model_copy(deep=True)

            task_hazard_args.site_params.vs30s = task_vs30s
            task_system_args.task_count = task_count

            branch.weight = 1.0
            slt = SourceLogicTree.from_branches([branch])
            task_hazard_args.hazard_model.srm_logic_tree = slt

            system_args.task_count = task_count
            yield build_task(task_hazard_args, task_system_args)
