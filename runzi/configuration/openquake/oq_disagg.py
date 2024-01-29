import copy
import os
import pwd
import itertools
import stat
from dataclasses import asdict
from pathlib import PurePath

import numpy as np

from nzshm_model.source_logic_tree import SourceLogicTree
import toshi_hazard_store

from .util import unpack_values, unpack_keys, update_oq_args, EC2_CONFIGS, ComputePlatform
from .oq_hazard import DEFAULT_HAZARD_CONFIG

from runzi.automation.scaling.toshi_api.openquake_hazard.openquake_hazard_task import HazardTaskType
from runzi.automation.scaling.toshi_api import ToshiApi, SubtaskType, ModelType, CreateGeneralTaskArgs
from runzi.automation.scaling.python_task_factory import get_factory
from runzi.util.aws import get_ecs_job_config, BatchEnvironmentSetting
import runzi.execute.openquake.oq_hazard_task
from runzi.automation.scaling.local_config import (
    WORK_PATH,
    USE_API,
    API_KEY,
    API_URL,
    CLUSTER_MODE,
    EnvMode,
    S3_URL,
    S3_REPORT_BUCKET
)

HAZARD_MAX_TIME = 20  # minutes

# BIGGER_LEVER = True
COMPUTE_PLATFORM = ComputePlatform.EC2
EC2_CONFIG = EC2_CONFIGS["BL_CONF_2"]  # BL_CONF_32_120

factory_class = get_factory(CLUSTER_MODE)
factory_task = runzi.execute.openquake.oq_hazard_task
task_factory = factory_class(WORK_PATH, factory_task, task_config_path=WORK_PATH)

dist_bin_edges = [
    0, 5.0, 10.0, 15.0, 20.0, 30.0, 40.0, 50.0, 60.0, 80.0,
    100.0, 140.0, 180.0, 220.0, 260.0, 320.0, 380.0, 500.0
]
DEFAULT_DISAGG_CONFIG = copy.deepcopy(DEFAULT_HAZARD_CONFIG)
DEFAULT_DISAGG_CONFIG["general"]["calculation_mode"] = "disaggregation"
DEFAULT_DISAGG_CONFIG["disagg"] = dict(
    max_sites_disagg=1,
    mag_bin_width=0.1999,
    distance_bin_width=10,
    coordinate_bin_width=5,
    num_epsilon_bins=16,
    disagg_outputs="TRT Mag Dist Mag_Dist TRT_Mag_Dist_Eps",
    disagg_bin_edges={'dist': dist_bin_edges},
)

GT_COUNTER = 0


def compute_hazard_at_poe(levels, values, poe, inv_time):
    rp = -inv_time / np.log(1 - poe)
    haz = np.exp(np.interp(np.log(1 / rp), np.flip(np.log(values)), np.flip(np.log(levels))))
    return haz


def get_target_level(
    hazard_model_id,
    location,
    vs30,
    imt,
    agg,
    poe,
    inv_time,
):

    hc = next(toshi_hazard_store.query_v3.get_hazard_curves([location], [vs30], [hazard_model_id], [imt], [agg]))
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
                task_module=runzi.execute.openquake.oq_hazard_task.__name__,
                time_minutes=int(HAZARD_MAX_TIME), memory=30720, vcpu=4,
                job_definition="Fargate-runzi-openquake-JD",
                extra_env=extra_env,
                use_compression=True
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
        args_list.append(dict(k=key, v=value))

    if USE_API:

        # create new task in toshi_api
        gt_args = CreateGeneralTaskArgs(
            agent_name=pwd.getpwuid(os.getuid()).pw_name,
            title=title,
            description=description,
        )\
            .set_argument_list(args_list)\
            .set_subtask_type(subtask_type)\
            .set_model_type(model_type)

        gt_id = toshi_api.general_task.create_task(gt_args)

    return gt_id


def build_disagg_tasks(subtask_type: SubtaskType, model_type: ModelType, args):
    task_count = 0

    extra_env = [
        BatchEnvironmentSetting(name="NZSHM22_HAZARD_STORE_STAGE", value="PROD"),
        BatchEnvironmentSetting(name="NZSHM22_HAZARD_STORE_REGION", value="ap-southeast-2"),
        BatchEnvironmentSetting(name="NZSHM22_HAZARD_STORE_NUM_WORKERS", value="1"),
    ]

    iterate = args["config_iterate"]
    iter_keys = unpack_keys(iterate)
    for location, vs30, poe, imt, agg in itertools.product(
        args["location_codes"],
        args["vs30s"],
        args["poes"],
        args["imts"],
        args["aggs"],
    ):
        target_level = get_target_level(
            args["hazard_model_id"],
            location,
            vs30,
            imt,
            agg,
            poe,
            args["inv_time"],
        )

        for iter_values in itertools.product(*unpack_values(iterate)):
            task_arguments = dict(
                hazard_model_id=args["hazard_model_id"],
                title=args["general"]["title"],
                description=args["general"]["description"],
                task_type=HazardTaskType.DISAGG.name,
                gmcm_logic_tree=args["gmcm_logic_tree"],
                model_type=model_type.name,
                location_list=[location],
                vs30=vs30,
                imt=imt,
                agg=agg,
                poe=poe,
                inv_time=args["inv_time"],
                level=target_level,
            )
            task_arguments["oq"] = DEFAULT_DISAGG_CONFIG  # default openquake config
            
            # overwrite with user specifiction
            update_oq_args(
                task_arguments["oq"], args["config_scalar"], iter_keys, iter_values,
            )

            print('')
            print('task arguments MERGED')
            print('==========================')
            print(task_arguments)
            print('==========================')
            print('')

            # This is done at the config level only because we use the GT to keep track a a single disaggegation (for
            # all logic tree brances). This would normally live at the run level
            gt_id = new_general_task(
                task_arguments,
                args["general"].get("title"),
                args["general"].get("description"),
                subtask_type,
                model_type,
            )

            # iterate over every branch of the logic tree to create a task
            new_gt_id = None
            task_count = 0
            for branch in args['srm_logic_tree']:
                if not new_gt_id:
                    new_gt_id = gt_id
                branch.weight = 1.0
                slt = SourceLogicTree.from_branches([branch])

                task_count += 1
                job_arguments = dict(
                    task_id=task_count,
                    general_task_id=gt_id,
                    use_api=USE_API,
                    sleep_multiplier=args["sleep_multiplier"]
                )
                task_arguments['srm_logic_tree'] = asdict(slt)
                yield build_task(task_arguments, job_arguments, task_count, extra_env), gt_id
