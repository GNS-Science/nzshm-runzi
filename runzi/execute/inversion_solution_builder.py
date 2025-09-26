import argparse
from abc import ABC, abstractmethod
import datetime as dt
import json
import logging
import platform
import time
import urllib.parse
import uuid
from pathlib import PurePath
from typing import cast

import git
from dateutil.tz import tzutc
from nshm_toshi_client.task_relation import TaskRelation
from py4j.java_gateway import GatewayParameters, JavaGateway, JavaObject
from typing import TYPE_CHECKING

from runzi.automation.scaling.file_utils import download_files, get_output_file_id
from runzi.automation.scaling.local_config import API_KEY, API_URL, S3_URL, SPOOF_INVERSION, WORK_PATH
from runzi.automation.scaling.toshi_api import ModelType, ToshiApi
from runzi.runners.inversion_inputs_v2 import InversionArgs, InversionSystemArgs, SubductionTaskArgs, InversionTaskArgs

logging.basicConfig(level=logging.INFO)

loglevel = logging.INFO
logging.getLogger('py4j.java_gateway').setLevel(loglevel)
logging.getLogger('nshm_toshi_client.toshi_client_base').setLevel(loglevel)
logging.getLogger('nshm_toshi_client.toshi_file').setLevel(loglevel)
logging.getLogger('urllib3').setLevel(loglevel)
logging.getLogger('git.cmd').setLevel(loglevel)

log = logging.getLogger(__name__)


# TODO: not super thrilled with having to [0] index every task argument. Is there a better solution?
class InversionSolutionBuilder(ABC):
    """
    Configure the python client for a InversionTask
    """

    def __init__(self, user_args: InversionArgs, system_args: InversionSystemArgs):

        self.user_args = user_args
        self.system_args = system_args

        # setup the java gateway binding
        self._gateway = JavaGateway(gateway_parameters=GatewayParameters(port=system_args.java_gateway_port))
        # repos = ["opensha", "nzshm-opensha", "nzshm-runzi"]
        # self._repoheads = get_repo_heads(PurePath(job_args['root_folder']), repos)
        self._output_folder = PurePath(system_args.working_path)

        headers = {"x-api-key": API_KEY}
        self._task_relation_api = TaskRelation(API_URL, None, with_schema_validation=True, headers=headers)
        self._toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)
        self.inversion_runner: JavaObject

    # the purpose of this method is simply to be explicit about creating the runner object.
    @abstractmethod
    def _get_runner(self) -> JavaObject:
        pass

    @abstractmethod
    def _set_mfd(self):
        pass

    @abstractmethod
    def _set_scaling_relationship(self):
        pass

    @abstractmethod
    def _domain_specific_setup(self):
        pass

    def _set_sa_params(self):
        cast(InversionArgs, self.user_args)
        self.inversion_runner.setInversionSeconds(
            int(self.user_args.task.max_inversion_time[0] * 60)
        ).setEnergyChangeCompletionCriteria(
            float(0), self.user_args.task.completion_energy[0], float(1)
        ).setSelectionInterval(
            self.user_args.task.selection_interval_secs[0]
        ).setNumThreadsPerSelector(
            self.user_args.task.selector_threads[0]
        ).setNonnegativityConstraintType(
            self.user_args.task.non_negativity_function[0]
        ).setPerturbationFunction(
            self.user_args.task.pertubation_function[0]
        )

        if (averaging_threads := self.user_args.task.averaging_threads[0]) is not None:
            self.inversion_runner.setInversionAveraging(
                averaging_threads, self.user_args.task.averaging_interval_secs[0]
            )

        if (cooling_schedule := self.user_args.task.cooling_schedule[0]) is not None:
            self.inversion_runner.setCoolingSchedule(cooling_schedule)

    @abstractmethod
    def _set_deformation_model(self):
        self.inversion_runner.setDeformationModel(self.user_args.task.deformation_model[0])

    def _set_constraint_weights(self):
        self.user_args = cast(InversionArgs, self.user_args)
        reweight = self.user_args.task.reweight[0]

        if reweight is not None:
            self.inversion_runner.setReweightTargetQuantity("MAD")

        mfd_equality_weight = self.user_args.task.mfd_equality_weight[0]
        mfd_inequality_weight = self.user_args.task.mfd_inequality_weight[0]
        mfd_uncertainty_weight = self.user_args.task.mfd_uncertainty_weight[0]
        mfd_uncertainty_power = self.user_args.task.mfd_uncertainty_power[0]
        mfd_uncertainty_scalar = self.user_args.task.mfd_uncertainty_scalar[0]

        if mfd_uncertainty_weight is not None:
            weight = 1.0 if reweight else mfd_uncertainty_weight
            self.inversion_runner.setUncertaintyWeightedMFDWeights(weight, mfd_uncertainty_power, mfd_uncertainty_scalar)
        if (mfd_equality_weight is not None) and (mfd_inequality_weight is not None):
            weight_eq = 1.0 if reweight else mfd_equality_weight
            weight_ineq = 1.0 if reweight else mfd_inequality_weight
            self.inversion_runner.setGutenbergRichterMFDWeights(weight_eq, weight_ineq)

        slip_rate_weighting_type = self.user_args.task.slip_rate_weighting_type[0],
        slip_rate_normalized_weight = self.user_args.task.slip_rate_normalized_weight[0],
        slip_rate_unnormalized_weight = self.user_args.task.slip_rate_unnormalized_weight[0],
        slip_uncertainty_scaling_factor = self.user_args.task.slip_uncertainty_scaling_factor[0]
        slip_rate_weight = self.user_args.task.slip_rate_weight[0]
        use_slip_scalings = self.user_args.task.use_slip_scaling[0]

        if slip_rate_weighting_type is not None:
            if slip_rate_weighting_type == 'UNCERTAINTY_ADJUSTED':
                self.inversion_runner.setSlipRateUncertaintyConstraint(slip_rate_weight, slip_uncertainty_scaling_factor)
            else:
                self.inversion_runner.setSlipRateConstraint(slip_rate_weighting_type, slip_rate_normalized_weight, slip_rate_unnormalized_weight)
        elif ((mfd_uncertainty_weight is not None) and (mfd_uncertainty_power is not None)) or (reweight):
            weight = 1.0 if reweight else mfd_uncertainty_weight
            self.inversion_runner.setUncertaintyWeightedMFDWeights( weight, mfd_uncertainty_power, mfd_uncertainty_scalar)
        else:
            raise ValueError("Neither eq/ineq , nor uncertainty weights provided for MFD constraint setup")
            
        # True means no slips scaling and vice-versa
        self.inversion_runner.setUnmodifiedSlipRateStdvs(not use_slip_scalings)


    def run(self):
        t0 = dt.datetime.now()

        # maybe the JVM App is a little slow to get listening
        time.sleep(0.2)
    
        # Wait for some more time, scaled by taskid to avoid S3 consistency issue
        time.sleep(self.system_args.task_count * 0.01)
        self.inversion_runner = self._get_runner()

        rupture_set_id = self.user_args.task.rupture_set_id[0]
        file_generator = get_output_file_id(self._toshi_api, rupture_set_id)  # for file by file ID
        rupture_set_info = download_files(self._toshi_api, file_generator, str(WORK_PATH), overwrite=False)

        API_GitVersion = self._gateway.entry_point.getGitVersion()

        log.info(f"Running nzshm-opensha {API_GitVersion}")

        initial_solution_id = self.user_args.task.initial_solution_id[0]
        if initial_solution_id is not None:
            file_generator = get_output_file_id(self._toshi_api, initial_solution_id)
            initial_solution_info = download_files(self._toshi_api, file_generator, str(WORK_PATH), overwrite=False)

        environment = {"host": platform.node(), "nzshm-opensha.version": API_GitVersion}

        if self.system_args.use_api:
            general_task_id = self.system_args.general_task_id
            # create new task in toshi_api
            task_id = self._toshi_api.automation_task.create_task(
                dict(
                    created=dt.datetime.now(tzutc()).isoformat(),
                    task_type="INVERSION",
                    model_type=self.user_args.general.model_type.name.upper(),
                ),
                arguments=self.user_args.model_dump(),
                environment=environment,
            )

            # link task to the parent task
            gt_conn = self._task_relation_api.create_task_relation(general_task_id, task_id)
            log.info(f"created task_relationship: {gt_conn} for at: {task_id} on GT: {general_task_id}")

            # link task to the input datafiles
            if rupture_set_id:
                self._toshi_api.automation_task.link_task_file(task_id, rupture_set_id, 'READ')

            if initial_solution_id is not None:
                self._toshi_api.automation_task.link_task_file(task_id, initial_solution_id, 'READ')

        else:
            task_id = str(uuid.uuid4())

        self._set_mfd()
        self._set_scaling_relationship()
        self._set_sa_params()
        self._set_deformation_model()

        rupture_set_filepath = rupture_set_info[rupture_set_id]['filepath']
        self.inversion_runner.setRuptureSetFile(rupture_set_filepath)

        if initial_solution_id is not None:
            self.inversion_runner.setInitialSolution(initial_solution_info[initial_solution_id]['filepath'])


        if not SPOOF_INVERSION:
            log.info("Starting inversion of up to %s minutes" % self.user_args.task.max_inversion_time[0])
            log.info("======================================")
            self.inversion_runner.runInversion()

        output_file = str(PurePath(self.system_args.working_path, f"NZSHM22_InversionSolution-{task_id}.zip"))
        # name the output file
        # outputfile = self._output_folder.joinpath(self.inversion_runner.getDescriptiveName()+ ".zip")
        # log.info("building %s started at %s" % (outputfile, dt.datetime.utcnow().isoformat()), end=' ')

        # output_file = str(PurePath(job_arguments['output_file']))
        if not SPOOF_INVERSION:
            self.inversion_runner.writeSolution(output_file)
        else:
            with open(output_file, 'w') as spoof:
                spoof.write("this is spoofed solution")

        t1 = dt.datetime.now()
        log.info("Inversion took %s secs" % (t1 - t0).total_seconds())

        # capture task metrics
        duration = (dt.datetime.now() - t0).total_seconds()

        metrics = {"SPOOF_INVERSION": True}
        if not SPOOF_INVERSION:
            # fecth metrics and convert Java Map to python dict
            jmetrics = self.inversion_runner.getSolutionMetrics()
            for k in jmetrics:
                metrics[k] = jmetrics[k]

        if self.user_args.general.model_type is ModelType.SUBDUCTION:
            table_rows_v1 = self.inversion_runner.getTabularSolutionMfds() if not SPOOF_INVERSION else []
            mfd_table_rows = {"MFD_CURVES": table_rows_v1}
        else:
            table_rows_v1 = self.inversion_runner.getTabularSolutionMfds() if not SPOOF_INVERSION else []
            table_rows_v2 = self.inversion_runner.getTabularSolutionMfdsV2() if not SPOOF_INVERSION else []
            mfd_table_rows = {"MFD_CURVES": table_rows_v1, "MFD_CURVES_V2": table_rows_v2}

        if self.system_args.use_api:
            # record the completed task
            done_args = {
                'task_id': task_id,
                'duration': duration,
                'result': "SUCCESS",
                'state': "DONE",
            }
            self._toshi_api.automation_task.complete_task(done_args, metrics)

            # and the log files, why not
            java_log_file = self._output_folder.joinpath(f"java_app.{self.system_args.java_gateway_port}.log")
            # pyth_log_file = self._output_folder.joinpath(f"python_script.{job_arguments['java_gateway_port']}.log")
            self._toshi_api.automation_task.upload_task_file(task_id, java_log_file, 'WRITE')
            # self._toshi_api.automation_task.upload_task_file(task_id, pyth_log_file, 'WRITE')

            # upload the task output
            predecessors = [
                dict(id=rupture_set_id, depth=-1),
            ]

            inversion_id = self._toshi_api.inversion_solution.upload_inversion_solution(
                task_id,
                filepath=output_file,
                meta=self.user_args.task.model_dump(),
                predecessors=predecessors,
                metrics=metrics,
            )
            log.info(f"created inversion solution: {inversion_id}")

            # Get the MFD tables...
            if not SPOOF_INVERSION:
                for table_type, table_rows in mfd_table_rows.items():
                    mfd_table_id = None

                    mfd_table_data = []
                    for row in table_rows:
                        mfd_table_data.append([x for x in row])

                    result = self._toshi_api.table.create_table(
                        mfd_table_data,
                        column_headers=["series", "series_name", "X", "Y"],
                        column_types=["integer", "string", "double", "double"],
                        object_id=inversion_id,
                        table_name="Inversion Solution MFD table",
                        table_type=table_type,
                        dimensions=None,
                    )
                    mfd_table_id = result['id']
                    result = self._toshi_api.inversion_solution.append_hazard_table(
                        inversion_id,
                        mfd_table_id,
                        label="Inversion Solution MFD table",
                        table_type=table_type,
                        dimensions=None,
                    )
                    log.info(f"created & linked table: {mfd_table_id}")

        else:
            log.info(metrics)
        log.info("; took %s secs" % (dt.datetime.now() - t0).total_seconds())

