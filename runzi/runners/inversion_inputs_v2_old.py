"""This module provides the Pydantic class for defining inversion job inputs."""

from pydantic import BaseModel, field_validator, field_serializer, ValidationInfo, model_validator
from typing import Any, Optional
from runzi.automation.scaling.toshi_api import SubtaskType, ModelType

class JobArgs(BaseModel):
    worker_pool_size: int
    jvm_heap_max: int
    java_threads: int
    use_api: bool
    general_task_id: str
    mock_mode: bool = False

class GeneralArgs(BaseModel):
    unique_id: Optional[str] = None
    task_title: str
    task_description: str
    file_id: str
    subtask_type: SubtaskType
    model_type: ModelType

    # we want to use the (case-insensitive) name for the model_type for input
    @field_validator('model_type', 'subtask_type', mode='before')
    @classmethod
    def convert_to_enum(cls, value: Any, info: ValidationInfo) -> ModelType | SubtaskType:
        if isinstance(value, (ModelType, SubtaskType)):
            return value
        try:
            if info.field_name == 'model_type':
                return ModelType[value.upper()]
            return SubtaskType[value.upper()]
        except (KeyError, AttributeError):
            try:
                if info.field_name == 'model_type':
                    return ModelType(value)
                return SubtaskType(value)
            except ValueError:
                raise ValueError("model_type input is not valid")

    # because we before-validate model_type to convert from a string of the enum name to enum
    # instance, we also want to serialize this way
    @field_serializer('subtask_type', 'model_type')
    def serialize_model_type(self, model_type: ModelType | SubtaskType, _info):
        return model_type.name

class ScalingC(BaseModel):
    tag: str
    dip: float
    strike: float

# TODO: which of these are actually optional?
# optional lists should be [None,] not None
# are all task args lists? I think so
class TaskArgs(BaseModel):
    rounds: Optional[list[int]] = None

    deformation_models: Optional[list[str]] = None

    initial_solution_ids: Optional[list[str]] = None

    completion_energies: Optional[list[float]] = None
    max_inversion_times: Optional[list[float]] = None
    selection_interval_secs: Optional[list[float]] = None
    threads_per_selector: Optional[list[int]] = None
    threads_per_selectors: Optional[list[int]] = None
    averaging_threads: Optional[list[int]] = None
    averaging_interval_secs: Optional[list[float]] = None
    perturbation_function: Optional[list[str]] = None
    perturbation_functions: Optional[list[str]] = None
    cooling_schedules: Optional[list[str]] = None

    scaling_c: Optional[list[dict[str, Any]]] = None
    scaling_c_vals: Optional[list[float]] = None
    scaling_relationships: Optional[list[str]] = None
    scaling_recalc_mags: Optional[list[bool]] = None
    b_and_n: Optional[list[dict[str, Any]]] = None

    spatial_seis_pdfs: Optional[list[str]] = None
    mfd_transition_mags: Optional[list[float]] = None
    mag_ranges: Optional[list[dict[str, Any]]] = None
    max_mag_types: Optional[list[str]] = None
    mfd_min_mags: Optional[list[float]] = None
    seismogenic_min_mags: Optional[list[float]] = None

    non_negativity_function: Optional[list[str]] = None
    non_negativity_functions: Optional[list[str]] = None

    slip_rate_factors: Optional[list[dict[str, Any]]] = None
    tvz_slip_rate_factors: Optional[list[float]] = None

    paleo_probability_models: Optional[list[str]] = None

    mfd_equality_weights: Optional[list[float]] = None
    mfd_inequality_weights: Optional[list[float]] = None
    paleo_rate_constraints: Optional[list[str]] = None
    mfd_uncertainty_powers: Optional[list[float]] = None
    mfd_uncertainty_scalars: Optional[list[float]] = None
    constraint_wts: Optional[list[dict[str, Any]]] = None
    slip_rate_weighting_types: Optional[list[str]] = None
    slip_rate_weights: Optional[list[Optional[float]]] = None
    slip_uncertainty_scaling_factors: Optional[list[Optional[float]]] = None
    slip_rate_unnormalized_weights: Optional[list[str]] = None

class InversionInput(BaseModel):
    config_version: Optional[str] = None
    job_args: JobArgs
    general_args: GeneralArgs
    task_args: TaskArgs

    def get_job_args(self) -> dict[str, Any]:
        return {f"_{k}":v for k, v in self.job_args.model_dump().items()}

    def get_task_args(self) -> dict[str, Any]:
        return {f"_{k}":v for k, v in self.task_args.model_dump().items()}

    def get_run_args(self) -> dict[str, Any]:
        return self.task_args.model_dump()

    def get_general_args(self) -> dict[str, Any]:
        return {f"_{k}":v for k, v in self.general_args.model_dump().items()}

    def get_config_version(self) -> dict[str, Any]:
        return self.config_version

    def get_all(self) -> dict[str, Any]:
        job_args = self.get_job_args()
        task_args = self.get_task_args()
        general_args = self.get_general_args()
        config_verison = {"_config_version": self.config_version}
        return config_verison | job_args | general_args | task_args


    # some model files put the file_id in job_args instead of general_args. We'll move it here
    @model_validator(mode='before')
    @classmethod
    def move_file_id(cls, data: Any) -> Any:
        if (data['job_args'].get('file_id') is not None) and (data['general_args'].get('file_id') is None):
            data['general_args']['file_id'] = data['job_args'].get('file_id')
            del data['job_args']['file_id']
        return data