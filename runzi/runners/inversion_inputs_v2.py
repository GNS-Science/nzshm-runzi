"""This module provides the Pydantic class for defining inversion job inputs."""

from itertools import product
from pathlib import Path
from typing import Generator, Optional, Any

from pydantic import BaseModel, FilePath, field_serializer, field_validator, ValidationInfo

from runzi.automation.scaling.toshi_api import ModelType, SubtaskType
from runzi.runners.runner_inputs import InputBase


class InversionSystemArgs(BaseModel):
    java_gateway_port: int = 0
    working_path: FilePath = Path()
    general_task_id: Optional[str] = None
    task_count: int = 0
    java_threads: int = 0
    java_gateway_port: int = 0
    opensha_root_folder: FilePath = Path()
    use_api: bool = False


class GeneralArgs(BaseModel):
    mock_mode: bool = False
    general_task_id: str
    unique_id: Optional[str] = None
    title: str
    description: str
    subtask_type: SubtaskType
    model_type: ModelType
    worker_pool_size: int
    jvm_heap_max: int
    java_threads: int
    root_folder: FilePath

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


class MFD(BaseModel):
    b: float
    N: float
    tag: str
    enable_tvz: bool = False
    b_tvz: float = 0.0  # not used if enable_tvz is False
    N_tvz: float = 0.0  # not used if enable_tvz is False


class ScalingC(BaseModel):
    dip: float
    strike: float
    tag: str


class MagRange(BaseModel):
    min_mag_sans: float
    min_mag_tvz: float
    max_mag_sans: float
    max_mag_tvz: float


class SlipRateFactor(BaseModel):
    tag: str
    sans: float
    tvz: float


# TODO: should these all be singular?
# TODO: chould make the fields e.g. list[float] | float. Leaves room for user error
# TODO: default should be [None,] not None or [] so field[0] evaluates to false (or [False,] ?)
class TaskArgs(BaseModel):
    max_inversion_times: list[float]
    completion_energies: list[float]
    rupture_set_ids: list[str]
    threads_per_selectors: list[int]
    averaging_threads: list[int]
    initial_solution_ids: list[str]
    deformation_models: list[str]
    mfd_equality_weights: list[float]
    mfd_inequality_weights: list[float]
    slip_rate_weighting_types: list[str]
    slip_rate_normalized_weights: list[str]
    slip_rate_unnormalized_weights: list[str]
    mfd_min_mags: list[float]
    mfds: list[MFD]
    mfd_transition_mags: list[float]
    mfd_uncertainty_weights: list[float]
    mfd_uncertainty_powers: list[float]
    mfd_uncertainty_scalars: list[float]
    scaling_relationship: list[str]
    scaling_recalc_mags: list[bool]
    scaling_c_vals: list[float]  # subduction (and crustal?)
    scaling_cs: list[ScalingC]  # crustal
    selection_interval_secs: list[int]
    non_negativity_functions: list[str]
    pertubation_functions: list[str]
    averaging_interval_secs: list[int]
    cooling_schedules: list[str]
    spatial_seis_pdfs: list[str]  # crustal
    reweights: list[bool]  # crustal
    min_mag_sans: list[float]  # crustal
    min_mag_tvz: list[float]  # crustal
    max_mag_types: list[str]  # crustal
    mag_ranges: list[MagRange]  # crustal
    slip_rate_factors: list[SlipRateFactor]
    use_slip_scalings: list[bool]  # crustal
    slip_uncertainty_weights: list[float]  # crustal
    slip_uncertainty_scaling_factors: list[float]  # crustal
    slip_rate_weights: list[float]  # crustal
    paleo_rate_constraint_weights: list[float]  # crustal
    paleo_parent_rate_smoothness_constraint_weights: list[float]  # crustal
    paleo_rate_constraints: list[str]  # crustal
    paleo_probability_models: list[str]  # crustal


class OpenshaArgs(InputBase):
    # java: JavaArgs
    general: GeneralArgs


class InversionArgs(OpenshaArgs):
    task: TaskArgs

    def get_task_args(self) -> Generator['InversionArgs', None, None]:

        # empty/default entries can be anything
        names = self.task.model_fields_set
        values = [getattr(self.task, name) for name in names]
        for task_combination in product(*values):
            task_args = {name: [ta] for name, ta in zip(names, task_combination)}
            yield type(self)(**task_args)

    def get_run_args(self) -> dict:
        return self.task.model_dump()
