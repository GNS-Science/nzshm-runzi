"""This module provides the Pydantic class for defining inversion job inputs."""

from itertools import product
from pathlib import Path
from typing import Any, Generator, Literal, Optional

from pydantic import BaseModel, FilePath, ValidationInfo, field_serializer, field_validator

from runzi.automation.scaling.toshi_api import ModelType, SubtaskType
from runzi.runners.runner_inputs import InputBase

# Because we use field[0] for the value of the field in the inversion task we need a sentinal for "not set".
# We use [None,] for this.
DEFAULT_FIELD = [None,]

class InversionSystemArgs(BaseModel):
    java_gateway_port: int = 0
    working_path: FilePath = Path()
    general_task_id: Optional[str] = None
    task_count: int = 0
    java_threads: int = 0
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
    max_mag_sans: float
    min_mag_tvz: float
    max_mag_tvz: float


class SlipRateFactor(BaseModel):
    tag: str
    sans: float
    tvz: float


# TODO: default should be [None,] not None or [] so field[0] can be tested `is None` as a sentinal for "not set"
class InversionTaskArgs(BaseModel):
    rupture_set_id: list[str | None] = DEFAULT_FIELD

    initial_solution_id: list[str | None] = DEFAULT_FIELD

    max_inversion_time: list[float | None] = DEFAULT_FIELD
    completion_energy: list[float | None] = DEFAULT_FIELD
    averaging_threads: list[int | None] = DEFAULT_FIELD
    averaging_interval_secs: list[int | None] = DEFAULT_FIELD
    selector_threads: list[int | None] = DEFAULT_FIELD
    selection_interval_secs: list[int | None] = DEFAULT_FIELD
    pertubation_function: list[str | None] = DEFAULT_FIELD
    cooling_schedule: list[str | None] = DEFAULT_FIELD
    non_negativity_function: list[str | None] = DEFAULT_FIELD

    scaling_relationship: list[str | None] = DEFAULT_FIELD  # describes a type of scaling relationship, e.g. "SIMPLE_SUBDUCTION"
    scaling_recalc_mag: list[bool | None] = DEFAULT_FIELD

    deformation_model: list[str | None] = DEFAULT_FIELD  # fault slip rates, could be FAULT_MODEL which uses rupture set, or some other model

    mfd: list[MFD | None] = DEFAULT_FIELD  # N and b value for both sans and tvz. Subduction only uses sans. tvz is deprecated

    reweight: list[bool | None] = DEFAULT_FIELD  # if true, must also have uncertainty weighting for mfd and slip rate

    # penalize mfd residuals normalized by uncertainty which is a "made up" function of mag
    mfd_uncertainty_weight: list[float | None] = DEFAULT_FIELD
    mfd_uncertainty_power: list[float | None] = DEFAULT_FIELD
    mfd_uncertainty_scalar: list[float | None] = DEFAULT_FIELD

    # or penalize mfd residuals in absolute terms
    mfd_equality_weight: list[float | None] = DEFAULT_FIELD
    mfd_inequality_weight: list[float | None] = DEFAULT_FIELD
    mfd_eq_ineq_transition_mag: list[float | None] = DEFAULT_FIELD  # magnitude at which to transition from equality to inequality constraint

    # penalize absolute and relative to uncertinaty slip rate residuals
    slip_rate_weighting_type: list[Literal["BOTH", "NORMALIZED", "UNNORMALIZED"] | None] = DEFAULT_FIELD
    slip_rate_normalized_weight: list[float | None] = DEFAULT_FIELD
    slip_rate_unnormalized_weight: list[float | None] = DEFAULT_FIELD

    # or penalize by uncerainty only
    use_slip_scaling: list[bool | None] = DEFAULT_FIELD
    slip_rate_uncertainty_weight: list[float | None] = DEFAULT_FIELD
    slip_uncertainty_scaling_factor: list[float | None] = DEFAULT_FIELD


class SubductionTaskArgs(InversionTaskArgs):
    scaling_c_val: list[float | None] = DEFAULT_FIELD  # subduction (and crustal?)
    mfd_min_mag: list[float | None] = DEFAULT_FIELD


class CrustalTaskArgs(InversionTaskArgs):
    spatial_seis_pdf: list[str | None] = DEFAULT_FIELD

    scaling_c_val: list[ScalingC | None] = DEFAULT_FIELD

    min_mag_sans: list[float | None] = DEFAULT_FIELD
    min_mag_tvz: list[float | None] = DEFAULT_FIELD
    max_mag_type: list[str | None] = DEFAULT_FIELD
    mag_range: list[MagRange | None] = DEFAULT_FIELD

    slip_rate_factor: list[SlipRateFactor | None] = DEFAULT_FIELD

    paleo_rate_constraint_weight: list[float | None] = DEFAULT_FIELD
    paleo_parent_rate_smoothness_constraint_weight: list[float | None] = DEFAULT_FIELD
    paleo_rate_constraint: list[str | None] = DEFAULT_FIELD
    paleo_probability_model: list[str | None] = DEFAULT_FIELD


class OpenshaArgs(InputBase):
    # java: JavaArgs
    general: GeneralArgs


class InversionArgs(OpenshaArgs):
    task: InversionTaskArgs

    def get_task_args(self) -> Generator['InversionArgs', None, None]:

        # empty/default entries can be anything
        names = self.task.model_fields_set
        values = [getattr(self.task, name) for name in names]
        for task_combination in product(*values):
            task_args = {name: [ta] for name, ta in zip(names, task_combination)}
            yield type(self).model_validate(task_args)

    def get_run_args(self) -> dict:
        return self.task.model_dump()


class SubductionInversionArgs(InversionArgs):
    task: SubductionTaskArgs


# WIP
class CrustalInversionArgs(InversionArgs):
    task: CrustalTaskArgs
