import os
import itertools
import stat
from pathlib import PurePath
from dataclasses import asdict

from nzshm_model.logic_tree import SourceLogicTree

from .util import unpack_keys, unpack_values, update_oq_args, ComputePlatform, EC2_CONFIGS
from runzi.automation.scaling.toshi_api import SubtaskType, ModelType
from runzi.automation.scaling.python_task_factory import get_factory
from runzi.util.aws import get_ecs_job_config, BatchEnvironmentSetting
from runzi.automation.scaling.toshi_api.openquake_hazard.openquake_hazard_task import HazardTaskType
import runzi.execute.openquake.oq_hazard_task
from runzi.automation.scaling.local_config import (
    WORK_PATH,
    USE_API,
    API_URL,
    CLUSTER_MODE,
    EnvMode,
    S3_URL,
    S3_REPORT_BUCKET
)

HAZARD_MAX_TIME = 48 * 60  # minutes

COMPUTE_PLATFORM = ComputePlatform.EC2
EC2_CONFIG = EC2_CONFIGS["BL_CONF_1"]  # BL_CONF_32_120

factory_class = get_factory(CLUSTER_MODE)
factory_task = runzi.execute.openquake.oq_hazard_task
task_factory = factory_class(WORK_PATH, factory_task, task_config_path=WORK_PATH)

DEFAULT_HAZARD_CONFIG = dict(
    general=dict(
        random_seed=25,
        calculation_mode='classical',
        ps_grid_spacing=30,
    ),
    logic_tree=dict(
        number_of_logic_tree_samples=0,
    ),
    erf=dict(
        rupture_mesh_spacing=4,
        width_of_mfd_bin=0.1,
        complex_fault_mesh_spacing=10.0,
        area_source_discretization=10.0,
    ),
    site_params=dict(
        reference_vs30_type='measured',
    ),
    calculation=dict(
        investigation_time=1.0,
        truncation_level=4,
        maximum_distance={
            'Active Shallow Crust': [(4.0, 0), (5.0, 100.0), (6.0, 200.0), (9.5, 300.0)],
            'Subduction Interface': [(5.0, 0), (6.0, 200.0), (10, 500.0)],
            'Subduction Intraslab': [(5.0, 0), (6.0, 200.0), (10, 500.0)]
        }
    ),
    output=dict(
        individual_curves='true',
    ),
)


def build_task(task_arguments, job_arguments, task_id, extra_env):

    if CLUSTER_MODE == EnvMode['AWS']:
        job_name = f"Runzi-automation-oq-hazard-{task_id}"
        config_data = dict(task_arguments=task_arguments, job_arguments=job_arguments)

        if COMPUTE_PLATFORM is ComputePlatform.EC2:
            return get_ecs_job_config(
                job_name,
                'N/A', config_data,
                toshi_api_url=API_URL, toshi_s3_url=S3_URL, toshi_report_bucket=S3_REPORT_BUCKET,
                task_module=runzi.execute.openquake.oq_hazard_task.__name__,
                time_minutes=int(HAZARD_MAX_TIME),
                memory=EC2_CONFIG["mem"],
                vcpu=EC2_CONFIG["cpu"],
                job_definition=EC2_CONFIG["job_def"],  # "BigLeverOnDemandEC2-JD", # "BiggerLever-runzi-openquake-JD", #"getting-started-job-definition-jun7",
                job_queue=EC2_CONFIG["job_queue"],
                extra_env=extra_env,
                use_compression=True
            )
        elif COMPUTE_PLATFORM is ComputePlatform.Fargate:
            return get_ecs_job_config(
                job_name,
                'N/A', config_data,
                toshi_api_url=API_URL, toshi_s3_url=S3_URL, toshi_report_bucket=S3_REPORT_BUCKET,
                task_module=runzi.execute.oq_hazard_task.__name__,
                time_minutes=int(HAZARD_MAX_TIME), memory=30720, vcpu=4,
                job_definition="Fargate-runzi-openquake-JD",
                extra_env=extra_env,
                use_compression=True
            )

    else:
        # write a config
        task_factory.write_task_config(task_arguments, job_arguments)
        script, task_number = task_factory.get_task_script()

        script_file_path = PurePath(WORK_PATH, f"task_{task_id}.sh")
        with open(script_file_path, 'w') as f:
            f.write(script)

        # make file executable
        st = os.stat(script_file_path)
        os.chmod(script_file_path, st.st_mode | stat.S_IEXEC)

        return str(script_file_path)


def build_hazard_tasks(general_task_id: str, subtask_type: SubtaskType, model_type: ModelType, subtask_arguments):

    extra_env = [
        BatchEnvironmentSetting(name="NZSHM22_HAZARD_STORE_STAGE", value="PROD"),
        BatchEnvironmentSetting(name="NZSHM22_HAZARD_STORE_REGION", value="ap-southeast-2"),
        BatchEnvironmentSetting(name="NZSHM22_HAZARD_STORE_NUM_WORKERS", value="1"),
    ]

    iterate = subtask_arguments["config_iterate"]
    iter_keys = unpack_keys(iterate)
    task_count = 0
    for vs30 in subtask_arguments["vs30s"]:
        for iter_values in itertools.product(*unpack_values(iterate)):
            task_arguments = dict(
                title=subtask_arguments["general"]["title"],
                description=subtask_arguments["general"]["description"],
                task_type=HazardTaskType.HAZARD.name,
                gmcm_logic_tree=subtask_arguments["gmcm_logic_tree"].to_dict(),
                model_type=model_type.name,
                intensity_spec=subtask_arguments["intensity_spec"],
                location_list=subtask_arguments["location_list"],
                vs30=vs30,
                disagg_conf=subtask_arguments["disagg_conf"],
            )

            task_arguments["oq"] = DEFAULT_HAZARD_CONFIG  # default openquake config
            
            # overwrite with user specifiction
            update_oq_args(
                task_arguments["oq"], subtask_arguments["config_scalar"], iter_keys, iter_values,
            )

            print('')
            print('task arguments MERGED')
            print('==========================')
            print(task_arguments)
            print('==========================')
            print('')

            for branch in subtask_arguments['srm_logic_tree']:
                branch.weight = 1.0
                slt = SourceLogicTree.from_branches([branch])

                task_count += 1
                job_arguments = dict(
                    task_id=task_count,
                    general_task_id=general_task_id,
                    use_api=USE_API,
                    sleep_multiplier=subtask_arguments["sleep_multiplier"],
                )
                task_arguments['srm_logic_tree'] = slt.to_dict()
                yield build_task(task_arguments, job_arguments, task_count, extra_env)
