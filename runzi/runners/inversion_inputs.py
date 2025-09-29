"""This module provides the Pydantic class for defining inversion job inputs."""

from itertools import product
from pathlib import Path
from typing import Any, Generator, Literal, Optional

from pydantic import BaseModel, FilePath, ValidationInfo, field_serializer, field_validator

from runzi.automation.scaling.toshi_api import ModelType, SubtaskType
from runzi.runners.runner_inputs import InputBase


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


# TODO: should these all be singular nouns?
# TODO: chould make the fields e.g. list[float] | float. Leaves room for user error
# TODO: default should be [None,] not None or [] so field[0] evaluates to false (or [False,] ?)
class InversionTaskArgs(BaseModel):
    rupture_set_id: list[str]

    initial_solution_id: list[str]

    max_inversion_time: list[float]
    completion_energy: list[float]
    averaging_threads: list[int]
    averaging_interval_secs: list[int]
    selector_threads: list[int]
    selection_interval_secs: list[int]
    pertubation_function: list[str]
    cooling_schedule: list[str]
    non_negativity_function: list[str]

    scaling_relationship: list[str]  # describes a type of scaling relationship, e.g. "SIMPLE_SUBDUCTION"
    scaling_recalc_mag: list[bool]

    deformation_model: list[str]  # fault slip rates, could be FAULT_MODEL which uses rupture set, or some other model

    mfd: list[MFD]  # N and b value for both sans and tvz. Subduction only uses sans. tvz is deprecated

    reweight: list[bool]  # if true, must also have uncertainty weighting for mfd and slip rate

    # penalize mfd residuals normalized by uncertainty which is a "made up" function of mag
    mfd_uncertainty_weight: list[float]
    mfd_uncertainty_power: list[float]
    mfd_uncertainty_scalar: list[float]

    # or penalize mfd residuals in absolute terms
    mfd_equality_weight: list[float]
    mfd_inequality_weight: list[float]
    mfd_eq_ineq_transition_mag: list[float]  # magnitude at which to transition from equality to inequality constraint

    # penalize absolute and relative to uncertinaty slip rate residuals
    slip_rate_weighting_type: list[
        Literal["BOTH", "NORMALIZED", "UNNORMALIZED", "NORMALIZED_BY_UNCERTAINTY", "UNCERTAINTY_ADJUSTED"]
    ]  # UNCERTAINTY_ADJUSTED is not a OpenSHA option, but a flag to use setSlipRateUncertaintyConstraint, not sure the difference between NORMALIZED_BY_UNCERTAINTY and UNCERTAINTY_ADJUSTED
    slip_rate_normalized_weight: list[float]
    slip_rate_unnormalized_weight: list[float]

    # or penalize by uncerainty only
    use_slip_scaling: list[bool]
    slip_rate_weight: list[float]
    slip_uncertainty_scaling_factor: list[float]


class SubductionTaskArgs(InversionTaskArgs):
    scaling_c_val: list[float]  # subduction (and crustal?)
    mfd_min_mag: list[float]


class CrustalTaskArgs(InversionTaskArgs):
    spatial_seis_pdf: list[str]

    scaling_c_val: list[ScalingC]

    min_mag_sans: list[float]
    min_mag_tvz: list[float]
    max_mag_type: list[str]
    mag_range: list[MagRange]

    slip_rate_factor: list[SlipRateFactor]

    paleo_rate_constraint_weight: list[float]
    paleo_parent_rate_smoothness_constraint_weight: list[float]
    paleo_rate_constraint: list[str]
    paleo_probability_model: list[str]


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
