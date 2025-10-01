"""This module provides the Pydantic class for defining inversion job inputs."""

from itertools import product
from pathlib import Path
from typing import Any, Generator, Literal, Optional, Sequence
from typing_extensions import Self

from pydantic import BaseModel, FilePath, ValidationInfo, field_serializer, field_validator, DirectoryPath, model_validator

from runzi.automation.scaling.toshi_api import ModelType, SubtaskType
from runzi.runners.runner_inputs import InputBase

# Because we use field[0] for the value of the field in the inversion task we need a sentinal for "not set".
# We use [None,] for this.
DEFAULT_FIELD = [None,]

class InversionSystemArgs(BaseModel):
    java_gateway_port: int = 0
    working_path: DirectoryPath = Path()
    general_task_id: Optional[str] = None
    task_count: int = 0
    java_threads: int = 0
    opensha_root_folder: DirectoryPath = Path()
    use_api: bool = False


class GeneralArgs(BaseModel):
    subtask_type: SubtaskType
    model_type: ModelType

    # we want to use the (case-insensitive) name for the model_type for input
    @field_validator('model_type', 'subtask_type', mode='before')
    @classmethod
    def _convert_to_enum(cls, value: Any, info: ValidationInfo) -> ModelType | SubtaskType:
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
    rupture_set_id: Sequence[str]

    initial_solution_id: Sequence[str | None] = DEFAULT_FIELD

    max_inversion_time: Sequence[float]
    completion_energy: Sequence[float]
    averaging_threads: Sequence[int | None] = DEFAULT_FIELD
    averaging_interval_secs: Sequence[int]
    selector_threads: Sequence[int]
    selection_interval_secs: Sequence[int]
    perturbation_function: Sequence[str]
    cooling_schedule: Sequence[str | None] = DEFAULT_FIELD
    non_negativity_function: Sequence[str]

    # describes a type of scaling relationship, e.g. "SIMPLE_SUBDUCTION"
    scaling_relationship: Sequence[str | None] = DEFAULT_FIELD
    scaling_recalc_mag: Sequence[bool | None] = DEFAULT_FIELD

    # fault slip rates, could be FAULT_MODEL which uses rupture set, or some other model
    deformation_model: Sequence[str]

    # N and b value for both sans and tvz. Subduction only uses sans. tvz is deprecated
    mfd: Sequence[MFD | None] = DEFAULT_FIELD  

    # if true, must also have uncertainty weighting for mfd and slip rate
    reweight: Sequence[bool | None] = DEFAULT_FIELD

    # penalize mfd residuals normalized by uncertainty which is a "made up" function of mag
    mfd_uncertainty_weight: Sequence[float | None] = DEFAULT_FIELD
    mfd_uncertainty_power: Sequence[float | None] = DEFAULT_FIELD
    mfd_uncertainty_scalar: Sequence[float | None] = DEFAULT_FIELD

    # or penalize mfd residuals in absolute terms
    mfd_equality_weight: Sequence[float | None] = DEFAULT_FIELD
    mfd_inequality_weight: Sequence[float | None] = DEFAULT_FIELD
    # magnitude at which to transition from equality to inequality constraint
    mfd_eq_ineq_transition_mag: Sequence[float | None] = DEFAULT_FIELD

    # penalize absolute and relative to uncertinaty slip rate residuals
    slip_rate_weighting_type: Sequence[Literal["BOTH", "NORMALIZED", "UNNORMALIZED"] | None] = DEFAULT_FIELD
    slip_rate_normalized_weight: Sequence[float | None] = DEFAULT_FIELD
    slip_rate_unnormalized_weight: Sequence[float | None] = DEFAULT_FIELD

    # or penalize by uncerainty only
    use_slip_scaling: Sequence[bool | None] = DEFAULT_FIELD
    slip_rate_uncertainty_weight: Sequence[float | None] = DEFAULT_FIELD
    slip_uncertainty_scaling_factor: Sequence[float | None] = DEFAULT_FIELD

    @model_validator(mode='after')
    def _check_reweight(self) -> Self:
        """If re-weighting, must use uncertinaty weighted constraints"""
        if self.reweight != DEFAULT_FIELD:
            if (self.mfd_uncertainty_weight == DEFAULT_FIELD) and (self.slip_rate_uncertainty_weight ==  DEFAULT_FIELD):
                raise ValueError("Re-weigting requires use of uncertainty weighted constraints for MFD and slip rate")
        return self

    @model_validator(mode='after')
    def _check_mfd_constraint(self) -> Self:
        """Choose either uncertainty weighted or eq/ineq constraints for MFD, not both."""
        if (self.mfd_uncertainty_weight != DEFAULT_FIELD) and (self.mfd_equality_weight != DEFAULT_FIELD):
            raise ValueError("Cannot combine uncertainty and equality/inequality MFD weights.")
        return self

    @model_validator(mode='after')
    def _check_mfd_unc_complete(self) -> Self:
        """If using uncertainty weighted MFD constraint, must specify all parameters."""
        if (self.mfd_uncertainty_weight != DEFAULT_FIELD):
            if (self.mfd_uncertainty_power == DEFAULT_FIELD) or (self.mfd_uncertainty_scalar == DEFAULT_FIELD):
                raise ValueError("If using uncertainty weighted MFD constraint, must also set uncertainty power and scalar parameters.")
        return self

    @model_validator(mode='after')
    def _check_mfd_eq_complete(self) -> Self:
        """If using eq/ineq MFD constraint, must specify all parameters."""
        params = [self.mfd_equality_weight, self.mfd_inequality_weight, self.mfd_eq_ineq_transition_mag]
        is_default = [param == DEFAULT_FIELD for param in params]
        if (not all(is_default)) and (any(is_default)):
            raise ValueError("If using equality/inequality MFD constraints, must set all parameters (equality weight, inequality weight, transition mag)")
        return self

    @model_validator(mode='after')
    def _check_mfd_unc_complete(self) -> Self:
        """If using uncertainty weighted MFD constraint, must specify all parameters."""
        params = [self.mfd_uncertainty_weight, self.mfd_uncertainty_power, self.mfd_uncertainty_scalar]
        is_default = [param == DEFAULT_FIELD for param in params]
        if (not all(is_default)) and (any(is_default)):
            raise ValueError("If using uncertainty weighted MFD constraints, must set all parameters (weight, power, and scalar)")
        return self

    @model_validator(mode='after')
    def _check_slip_abs_complete(self) -> Self:
        """If using 'regular' slip rate constraint, must specify all parameters."""
        params = [self.slip_rate_weighting_type, self.slip_rate_normalized_weight, self.slip_rate_unnormalized_weight]
        is_default = [param == DEFAULT_FIELD for param in params]
        if (not all(is_default)) and (any(is_default)):
            raise ValueError("If using uncertainty weighted slip rate constraints, must set all parameters (slip weighting type, normalized weight, unnormalized weight")
        return self
        
    @model_validator(mode='after')
    def _check_slip_unc_complete(self) -> Self:
        """If using uncertainty weighted slip rate constraint, must specify all parameters."""
        params = [self.use_slip_scaling, self.slip_rate_uncertainty_weight, self.slip_uncertainty_scaling_factor]
        is_default = [param == DEFAULT_FIELD for param in params]
        if (not all(is_default)) and (any(is_default)):
            raise ValueError("If using uncertainty weighted slip rate constraints, must set all parameters (slip scaling boolean, weight, and scaling factor)")
        return self

    def get_tasks(self) -> Generator[Self, None, None]:
        names = self.model_fields_set
        values = [getattr(self, name) for name in names]
        for task_combination in product(*values):
            task_args = {name: [ta] for name, ta in zip(names, task_combination)}
            yield self.model_validate(task_args)



class SubductionTaskArgs(InversionTaskArgs):
    scaling_c_val: Sequence[float | None] = DEFAULT_FIELD
    mfd_min_mag: Sequence[float]


class CrustalTaskArgs(InversionTaskArgs):
    spatial_seis_pdf: Sequence[str | None] = DEFAULT_FIELD

    scaling_c_val: Sequence[ScalingC | None] = DEFAULT_FIELD

    min_mag_sans: Sequence[float]
    min_mag_tvz: Sequence[float]
    max_mag_type: Sequence[str]
    mag_range: Sequence[MagRange]

    slip_rate_factor: Sequence[SlipRateFactor]

    paleo_rate_constraint_weight: Sequence[float | None] = DEFAULT_FIELD
    paleo_parent_rate_smoothness_constraint_weight: Sequence[float | None] = DEFAULT_FIELD
    paleo_rate_constraint: Sequence[str | None] = DEFAULT_FIELD
    paleo_probability_model: Sequence[str | None] = DEFAULT_FIELD


# TODO: do we need this? Work through the other OpenSHA tasks (e.g. reports) to find out
class OpenshaArgs(InputBase):
    general: GeneralArgs


class InversionArgs(OpenshaArgs):
    task: InversionTaskArgs

    def get_tasks(self) -> Generator[Self, None, None]:
        for task in self.task.get_tasks():
            inv_args = self.model_copy(deep=True)
            inv_args.task = task
            yield inv_args

    def get_run_args(self) -> dict:
        return self.task.model_dump()


class SubductionInversionArgs(InversionArgs):
    task: SubductionTaskArgs


# WIP
class CrustalInversionArgs(InversionArgs):
    task: CrustalTaskArgs
