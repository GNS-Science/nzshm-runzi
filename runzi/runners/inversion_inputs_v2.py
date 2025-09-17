"""This module provides the Pydantic class for defining inversion job inputs."""

from pydantic import BaseModel, field_validator, field_serializer, ValidationInfo, model_validator
from typing import Any, Optional
from runzi.automation.scaling.toshi_api import SubtaskType, ModelType

class JobArgs(BaseModel):
    pass

class GeneralArgs(BaseModel):
    pass


class TaskArgs(BaseModel):
    pass

class InversionInput(BaseModel):
    pass