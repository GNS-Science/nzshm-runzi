import datetime as dt
import logging
import platform
import shutil
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Generator
from itertools import product
from pathlib import Path
from typing import Any, Literal, Self, cast
from zipfile import ZIP_DEFLATED, ZipFile

from dateutil.tz import tzutc
from nshm_toshi_client.task_relation import TaskRelation
from py4j.java_gateway import GatewayParameters, JavaGateway, JavaObject
from pydantic import BaseModel, model_validator

from runzi.arguments import TaskRuntimeArgs, serialize_arguments
from runzi.automation.file_utils import download_files, get_output_file_id
from runzi.automation.local_config import API_URL, S3_URL, SPOOF, WORK_PATH, get_auth_kwargs
from runzi.automation.toshi_api import ModelType, ToshiApi
from runzi.tasks.validators import all_or_none, more_than_one

logging.basicConfig(level=logging.INFO)

loglevel = logging.INFO
logging.getLogger('py4j.java_gateway').setLevel(loglevel)
logging.getLogger('nshm_toshi_client.toshi_client_base').setLevel(loglevel)
logging.getLogger('nshm_toshi_client.toshi_file').setLevel(loglevel)
logging.getLogger('urllib3').setLevel(loglevel)
logging.getLogger('git.cmd').setLevel(loglevel)

log = logging.getLogger(__name__)


class InversionArgs(BaseModel):
    """Inversion Arguments.

    Validators:
        - If using re-weighting, must also use uncertainty weighted constraints.
        - Must use either uncertainty weighted or eq/ineq constraints for MFD, not both.
        - If using eq/ineq MFD constraint, must specify all relevant parameters.
        - If using uncertainty weighted MFD constraint, must specify all parameters.
        - Cannot use uncertainty weighted and 'regular' slip constraints, not both.
        - If using 'regular' slip rate constraint, must specify all relevent parameters.
        - If using uncertainty weighted slip rate constraint, must specify all parameters.
    """

    class MFD(BaseModel):
        b: float
        N: float
        tag: str
        enable_tvz: bool = False
        b_tvz: float = 0.0
        """Not used if enable_tvz is False."""

        N_tvz: float = 0.0
        """Not used if enable_tvz is False."""

    class RuptureSet(BaseModel):
        rupture_set_id: str
        tag: str

    rupture_set: RuptureSet
    initial_solution_id: str | None = None

    max_inversion_time: float
    """Maximum time to run inversion in minutes."""

    completion_energy: float
    """Completion energy criterion. Ignored if 0."""

    averaging_threads: int | None = None
    averaging_interval_secs: int
    selector_threads: int
    selection_interval_secs: int
    perturbation_function: str
    cooling_schedule: str | None = None
    non_negativity_function: str

    scaling_relationship: str | None = None
    """Type of scaling relationship, e.g. 'SIMPLE_SUBDUCTION'."""

    scaling_recalc_mag: bool | None = None
    """Recaculate magnitudes using scaling relationship if True."""

    deformation_model: str
    """The fault slip rates, could be FAULT_MODEL which uses rupture set, or some other model."""

    mfd: MFD
    """N and b value for both sans and tvz. Subduction only uses sans. tvz is deprecated."""

    reweight: bool | None = None
    """If True, must also have uncertainty weighting for mfd and slip rate."""

    mfd_uncertainty_weight: float | None = None
    """Used to when penalizing MFD residuals normalized by uncertainty."""

    mfd_uncertainty_power: float | None = None
    """Used to when penalizing MFD residuals normalized by uncertainty."""

    mfd_uncertainty_scalar: float | None = None
    """Used to when penalizing MFD residuals normalized by uncertainty."""

    mfd_equality_weight: float | None = None
    """Used to penalize MFD residuals in absolute terms (no normalization)."""

    mfd_inequality_weight: float | None = None
    mfd_eq_ineq_transition_mag: float | None = None
    """Magnitude at which to transition from equality to inequality constraint."""

    slip_rate_weighting_type: Literal["BOTH", "NORMALIZED", "UNNORMALIZED"] | None = None
    """Penalize absolute and relative to uncertinaty slip rate residuals."""

    slip_rate_normalized_weight: float | None = None
    """Penalize absolute and relative to uncertinaty slip rate residuals."""

    slip_rate_unnormalized_weight: float | None = None
    """Penalize absolute and relative to uncertinaty slip rate residuals."""

    use_slip_scaling: bool | None = None
    """Penalize slip rate by uncerainty only."""

    slip_rate_uncertainty_weight: float | None = None
    """Penalize slip rate by uncerainty only."""

    slip_uncertainty_scaling_factor: float | None = None
    """Penalize slip rate by uncerainty only."""

    matrix_dump: bool = False
    """Dump A and d matrices to working directory. Inversion does not run."""

    @model_validator(mode='after')
    def check_reweight(self) -> Self:
        """If re-weighting, must use uncertinaty weighted constraints"""
        if self.reweight is not None:
            if (self.mfd_uncertainty_weight is None) and (self.slip_rate_uncertainty_weight is None):
                # TODO: this isn't true, reweighting overrides the weight,
                # but this test does make sure we have the other parameters, so maybe useful?
                raise ValueError("Re-weigting requires use of uncertainty weighted constraints for MFD and slip rate")
        return self

    @model_validator(mode='after')
    def check_mfd_constraint(self) -> Self:
        """Choose either uncertainty weighted or eq/ineq constraints for MFD, not both."""
        if more_than_one([self.mfd_uncertainty_weight, self.mfd_equality_weight]):
            raise ValueError("Cannot combine uncertainty and equality/inequality MFD weights.")
        return self

    @model_validator(mode='after')
    def check_mfd_eq_complete(self) -> Self:
        """If using eq/ineq MFD constraint, must specify all parameters."""
        params = [self.mfd_equality_weight, self.mfd_inequality_weight, self.mfd_eq_ineq_transition_mag]
        if not all_or_none(params):
            raise ValueError(
                "If using equality/inequality MFD constraints, must set all parameters (equality weight, "
                "inequality weight, transition mag)"
            )
        return self

    @model_validator(mode='after')
    def check_mfd_unc_complete(self) -> Self:
        """If using uncertainty weighted MFD constraint, must specify all parameters."""
        params = [self.mfd_uncertainty_weight, self.mfd_uncertainty_power, self.mfd_uncertainty_scalar]
        if not all_or_none(params):
            raise ValueError(
                "If using uncertainty weighted MFD constraints, must set all parameters (weight, power, and scalar)"
            )
        return self

    @model_validator(mode='after')
    def check_slip_constraint(self) -> Self:
        """Choose either uncertainty weighted or 'regular' slip constraints, not both."""
        if more_than_one([self.slip_rate_normalized_weight, self.slip_rate_uncertainty_weight]):
            raise ValueError("Cannot combine uncertainty and 'regular' slip rate constraints.")
        return self

    @model_validator(mode='after')
    def check_slip_abs_complete(self) -> Self:
        """If using 'regular' slip rate constraint, must specify all parameters."""
        params = [self.slip_rate_weighting_type, self.slip_rate_normalized_weight, self.slip_rate_unnormalized_weight]
        if not all_or_none(params):
            raise ValueError(
                "If using normalized/unnormalized slip rate constraints, must set all parameters (slip "
                "weighting type, normalized weight, unnormalized weight"
            )
        return self

    @model_validator(mode='after')
    def check_slip_unc_complete(self) -> Self:
        """If using uncertainty weighted slip rate constraint, must specify all parameters."""
        params = [self.use_slip_scaling, self.slip_rate_uncertainty_weight, self.slip_uncertainty_scaling_factor]
        if not all_or_none(params):
            raise ValueError(
                "If using uncertainty weighted slip rate constraints, must set all parameters (slip "
                "scaling boolean, weight, and scaling factor)"
            )
        return self

    def get_tasks(self) -> Generator[Self, None, None]:
        names = self.model_fields_set
        values = [getattr(self, name) for name in names]
        for task_combination in product(*values):
            task_args = {name: [ta] for name, ta in zip(names, task_combination, strict=True)}
            yield self.model_validate(task_args)


class InversionSolutionBuilder(ABC):
    """
    Configure the python client for a InversionTask
    """

    def __init__(self, user_args: InversionArgs, runtime_args: TaskRuntimeArgs, model_type: ModelType):

        self.user_args = user_args
        self.runtime_args = runtime_args
        self.model_type = model_type

        # setup the java gateway binding
        self.gateway = JavaGateway(gateway_parameters=GatewayParameters(port=runtime_args.java_gateway_port))
        # repos = ["opensha", "nzshm-opensha", "nzshm-runzi"]
        # self._repoheads = get_repo_heads(PurePath(job_args['root_folder']), repos)
        self.output_folder = WORK_PATH
        self.task_relation_api = TaskRelation(API_URL, None, with_schema_validation=False, **get_auth_kwargs())
        self.toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=False, **get_auth_kwargs())
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
            int(self.user_args.max_inversion_time * 60)
        ).setEnergyChangeCompletionCriteria(float(0), self.user_args.completion_energy, float(1)).setSelectionInterval(
            self.user_args.selection_interval_secs
        ).setNumThreadsPerSelector(self.user_args.selector_threads).setNonnegativityConstraintType(
            self.user_args.non_negativity_function
        ).setPerturbationFunction(self.user_args.perturbation_function)

        if (averaging_threads := self.user_args.averaging_threads) is not None:
            self.inversion_runner.setInversionAveraging(averaging_threads, self.user_args.averaging_interval_secs)

        if (cooling_schedule := self.user_args.cooling_schedule) is not None:
            self.inversion_runner.setCoolingSchedule(cooling_schedule)

    @abstractmethod
    def _set_deformation_model(self):
        self.inversion_runner.setDeformationModel(self.user_args.deformation_model)

    def _set_constraint_weights(self):
        self.user_args = cast(InversionArgs, self.user_args)
        reweight = self.user_args.reweight

        if reweight:
            self.inversion_runner.setReweightTargetQuantity("MAD")

        mfd_equality_weight = self.user_args.mfd_equality_weight
        mfd_inequality_weight = self.user_args.mfd_inequality_weight
        mfd_uncertainty_weight = self.user_args.mfd_uncertainty_weight
        mfd_uncertainty_power = self.user_args.mfd_uncertainty_power
        mfd_uncertainty_scalar = self.user_args.mfd_uncertainty_scalar

        if mfd_uncertainty_weight is not None:
            weight = 1.0 if reweight else mfd_uncertainty_weight
            self.inversion_runner.setUncertaintyWeightedMFDWeights(
                weight, mfd_uncertainty_power, mfd_uncertainty_scalar
            )
        elif (mfd_equality_weight is not None) and (mfd_inequality_weight is not None):
            self.inversion_runner.setGutenbergRichterMFDWeights(mfd_equality_weight, mfd_inequality_weight)

        slip_rate_weighting_type = self.user_args.slip_rate_weighting_type
        slip_rate_normalized_weight = self.user_args.slip_rate_normalized_weight
        slip_rate_unnormalized_weight = self.user_args.slip_rate_unnormalized_weight
        slip_uncertainty_scaling_factor = self.user_args.slip_uncertainty_scaling_factor
        slip_rate_uncertainty_weight = self.user_args.slip_rate_uncertainty_weight
        use_slip_scalings = self.user_args.use_slip_scaling

        if slip_rate_uncertainty_weight is not None:
            weight = 1.0 if reweight else slip_rate_uncertainty_weight
            self.inversion_runner.setSlipRateUncertaintyConstraint(
                weight,
                slip_uncertainty_scaling_factor,
            ).setUnmodifiedSlipRateStdvs(not use_slip_scalings)  # True means no slips scaling and vice-versa
        elif (slip_rate_normalized_weight) and (slip_rate_unnormalized_weight is not None):
            self.inversion_runner.setSlipRateConstraint(
                slip_rate_weighting_type, slip_rate_normalized_weight, slip_rate_unnormalized_weight
            )

    def _complete_task(self, task_id: str, t0: dt.datetime, metrics: dict[str, Any] | None = None) -> None:
        """Mark the toshi task DONE and upload the java log.

        Args:
            task_id: the toshi automation task id.
            t0: when the task started, for the reported duration.
            metrics: optional task metrics to record alongside the completion.
        """
        done_args = {
            'task_id': task_id,
            'duration': (dt.datetime.now() - t0).total_seconds(),
            'result': "SUCCESS",
            'state': "DONE",
        }
        self.toshi_api.automation_task.complete_task(done_args, metrics)

        # and the log files, why not
        java_log_file = self.output_folder.joinpath(f"java_app.{self.runtime_args.java_gateway_port}.log")
        # pyth_log_file = self.output_folder.joinpath(f"python_script.{self.runtime_args.java_gateway_port}.log")
        self.toshi_api.automation_task.upload_task_file(task_id, java_log_file, 'WRITE')
        # self.toshi_api.automation_task.upload_task_file(task_id, pyth_log_file, 'WRITE')

    def _write_matrices(self, task_id: str, output_filepath: Path, t0: dt.datetime):
        matrix_dump_path = WORK_PATH / f"{task_id}_matrices"
        if not matrix_dump_path.exists():
            matrix_dump_path.mkdir()
        try:
            if SPOOF:
                with open(output_filepath, 'w') as spoof:
                    spoof.write("this is a spoofed matrix")
            else:
                self.inversion_runner.setMatrixDumpPath(str(matrix_dump_path))
                self.inversion_runner.runInversion()
                with ZipFile(output_filepath, 'w', compression=ZIP_DEFLATED) as archive:
                    for file_path in sorted(matrix_dump_path.iterdir()):
                        archive.write(file_path, arcname=file_path.name)

            if self.runtime_args.use_api:
                # record the completed task
                self._complete_task(task_id, t0)

                # upload the task output. NB a File has no predecessors field, so the rupture set
                # lineage is carried by the meta (and by the task's own READ file relation).
                matrices_id = self.toshi_api.automation_task.upload_file(
                    output_filepath,
                    meta=self.user_args.model_dump(),
                )
                self.toshi_api.automation_task.link_task_file(task_id, matrices_id, 'WRITE')
                log.info('created inversion matrices: %s', matrices_id)
        finally:
            shutil.rmtree(matrix_dump_path, ignore_errors=True)

    def _run_inversion(self, task_id: str, output_filepath: Path, rupture_set_id: str, t0: dt.datetime):
        if not SPOOF:
            self.inversion_runner.runInversion()
            self.inversion_runner.writeSolution(str(output_filepath))
        else:
            with open(output_filepath, 'w') as spoof:
                spoof.write("this is spoofed solution")

        t1 = dt.datetime.now()
        log.info('Inversion took %s secs', (t1 - t0).total_seconds())

        # capture task metrics
        metrics = {"message": "getSolutionMetrics has been removed from OpenSHA"}

        # TODO: put these back in when/if function is re-introduced to opensha
        if self.model_type is ModelType.SUBDUCTION:
            # table_rows_v1 = self.inversion_runner.getTabularSolutionMfds() if not SPOOF else []
            table_rows_v1: list[Any] = []
            mfd_table_rows = {"MFD_CURVES": table_rows_v1}
        else:
            # table_rows_v1 = self.inversion_runner.getTabularSolutionMfds() if not SPOOF else []
            # table_rows_v2 = self.inversion_runner.getTabularSolutionMfdsV2() if not SPOOF else []
            table_rows_v1 = []
            table_rows_v2: list[Any] = []
            mfd_table_rows = {"MFD_CURVES": table_rows_v1, "MFD_CURVES_V2": table_rows_v2}

        if self.runtime_args.use_api:
            # record the completed task
            self._complete_task(task_id, t0, metrics)

            # upload the task output
            predecessors = [
                dict(id=rupture_set_id, depth=-1),
            ]

            inversion_id = self.toshi_api.inversion_solution.upload_inversion_solution(
                task_id,
                filepath=output_filepath,
                meta=self.user_args.model_dump(),
                predecessors=predecessors,
                metrics=metrics,
            )
            log.info('created inversion solution: %s', inversion_id)

            # Get the MFD tables...
            if not SPOOF:
                for table_type, table_rows in mfd_table_rows.items():
                    mfd_table_id = None

                    mfd_table_data = []
                    for row in table_rows:
                        mfd_table_data.append([x for x in row])

                    result = self.toshi_api.table.create_table(
                        mfd_table_data,
                        column_headers=["series", "series_name", "X", "Y"],
                        column_types=["integer", "string", "double", "double"],
                        object_id=inversion_id,
                        table_name="Inversion Solution MFD table",
                        table_type=table_type,
                        dimensions=None,
                    )
                    mfd_table_id = result['id']
                    result = self.toshi_api.inversion_solution.append_hazard_table(
                        inversion_id,
                        mfd_table_id,
                        label="Inversion Solution MFD table",
                        table_type=table_type,
                        dimensions=None,
                    )
                    log.info('created & linked table: %s', mfd_table_id)

        else:
            log.info(metrics)
        log.info('Inversion task took %s secs', (dt.datetime.now() - t0).total_seconds())

    def run(self):
        t0 = dt.datetime.now()

        # Wait for some more time, scaled by taskid to avoid S3 consistency issue
        time.sleep(self.runtime_args.task_count * 0.01)
        self.inversion_runner = self._get_runner()

        rupture_set_id = self.user_args.rupture_set.rupture_set_id
        file_generator = get_output_file_id(self.toshi_api, rupture_set_id)  # for file by file ID
        rupture_set_info = download_files(self.toshi_api, file_generator, str(WORK_PATH), overwrite=False)

        API_GitVersion = self.gateway.entry_point.getGitVersion()

        log.info('Running nzshm-opensha %s', API_GitVersion)

        initial_solution_id = self.user_args.initial_solution_id
        if initial_solution_id is not None:
            file_generator = get_output_file_id(self.toshi_api, initial_solution_id)
            initial_solution_info = download_files(self.toshi_api, file_generator, str(WORK_PATH), overwrite=False)

        environment = {"host": platform.node(), "nzshm-opensha.version": API_GitVersion}

        if self.runtime_args.use_api:
            general_task_id = self.runtime_args.general_task_id
            # create new task in toshi_api
            task_id = self.toshi_api.automation_task.create_task(
                dict(
                    created=dt.datetime.now(tzutc()).isoformat(),
                    task_type="INVERSION",
                    model_type=self.model_type.name.upper(),
                    # general_task_id=general_task_id,
                ),
                arguments=serialize_arguments(self.user_args),
                environment=environment,
            )

            # link task to the parent task
            gt_conn = self.task_relation_api.create_task_relation(general_task_id, task_id)
            log.info('created task_relationship: %s for at: %s on GT: %s', gt_conn, task_id, general_task_id)

            # link task to the input datafiles
            if rupture_set_id:
                self.toshi_api.automation_task.link_task_file(task_id, rupture_set_id, 'READ')

            if initial_solution_id is not None:
                self.toshi_api.automation_task.link_task_file(task_id, initial_solution_id, 'READ')

        else:
            task_id = str(uuid.uuid4())

        self._set_mfd()
        self._set_scaling_relationship()
        self._set_sa_params()
        self._set_deformation_model()
        self._set_constraint_weights()
        self._domain_specific_setup()

        rupture_set_filepath = rupture_set_info[rupture_set_id]['filepath']
        self.inversion_runner.setRuptureSetFile(rupture_set_filepath)

        if initial_solution_id is not None:
            self.inversion_runner.setInitialSolution(initial_solution_info[initial_solution_id]['filepath'])

        if self.user_args.matrix_dump:
            output_filepath = WORK_PATH / f"NZSHM22_Matrices-{task_id}.zip"
            log.info('Building and dumping A and d matrices.')
            log.info("======================================")
            self._write_matrices(task_id, output_filepath, t0)
        else:
            output_filepath = WORK_PATH / f"NZSHM22_InversionSolution-{task_id}.zip"
            log.info('Starting inversion of up to %s minutes', self.user_args.max_inversion_time)
            log.info("======================================")
            self._run_inversion(task_id, output_filepath, rupture_set_id, t0)
