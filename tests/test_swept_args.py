import json
from math import prod
from typing import Self

import pytest
from pydantic import BaseModel, ValidationError, model_validator

from runzi.arguments import ArgSweeper


class SimpleArgs(BaseModel):
    class ComplexThing(BaseModel):
        a: int
        b: str

    param_a: int
    param_b: float
    param_c: str
    param_d: ComplexThing


class ConstrainedArgs(BaseModel):
    value: int
    threshold: int = 10

    @model_validator(mode='after')
    def value_below_threshold(self) -> Self:
        if self.value >= self.threshold:
            raise ValueError(f'value {self.value} must be less than threshold {self.threshold}')
        return self


def test_swept_args():

    data = {"param_a": 1, "param_b": 0.1, "param_c": "foo", "param_d": {"a": 10, "b": "x"}}
    prototype = SimpleArgs(**data)
    swept_args = {"param_a": [1, 2, 3], "param_d": [{"a": 101, "b": "X"}, {"a": 102, "b": "Y"}]}
    swept = ArgSweeper(prototype, swept_args, title="simple test", description="a simple args class")
    ntasks = len(list(swept.get_tasks()))
    assert ntasks == prod([len(v) for v in swept_args.values()])


def test_validate_all_tasks_passes_valid_swept_args():
    prototype = ConstrainedArgs(value=1)
    swept_args = {"value": [1, 2, 9]}
    sweeper = ArgSweeper(prototype, swept_args, title="t", description="d")
    sweeper.validate_all_tasks()  # no exception — all values < threshold


def test_validate_all_tasks_raises_on_invalid_swept_combination():
    prototype = ConstrainedArgs(value=1)
    swept_args = {"value": [1, 5, 10]}  # 10 == threshold → invalid
    sweeper = ArgSweeper(prototype, swept_args, title="t", description="d")
    with pytest.raises(ValidationError):
        sweeper.validate_all_tasks()


def test_validate_all_tasks_no_swept_args_valid():
    prototype = ConstrainedArgs(value=5)
    sweeper = ArgSweeper(prototype, {}, title="t", description="d")
    sweeper.validate_all_tasks()  # no exception


def test_validate_all_tasks_no_swept_args_invalid_after_mutation():
    prototype = ConstrainedArgs(value=1)
    sweeper = ArgSweeper(prototype, {}, title="t", description="d")
    # Simulate a runner __init__ mutating prototype_args without re-validating
    object.__setattr__(sweeper.prototype_args, 'value', 99)
    with pytest.raises(ValidationError):
        sweeper.validate_all_tasks()


def test_get_tasks_still_works_after_validate_all_tasks():
    prototype = ConstrainedArgs(value=1)
    swept_args = {"value": [1, 2, 3]}
    sweeper = ArgSweeper(prototype, swept_args, title="t", description="d")
    sweeper.validate_all_tasks()
    # Generator is recreated each call — full iteration still works
    assert len(list(sweeper.get_tasks())) == 3


def _write_config(tmp_path, **extra) -> str:
    config = {
        "title": "t",
        "description": "d",
        "param_a": 1,
        "param_b": 0.1,
        "param_c": "foo",
        "param_d": {"a": 1, "b": "x"},
        **extra,
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    return str(path)


def test_from_config_file_parses_submission_arg_overrides(tmp_path):
    path = _write_config(tmp_path, submission_arg_overrides={"ecs_memory": 2048})
    sweeper = ArgSweeper.from_config_file(path, SimpleArgs)
    assert sweeper.submission_arg_overrides == {"ecs_memory": 2048}


def test_from_config_file_rejects_renamed_sys_arg_overrides(tmp_path):
    """The old key was renamed; a config that still uses it is rejected as an unknown field."""
    path = _write_config(tmp_path, sys_arg_overrides={"ecs_memory": 2048})
    with pytest.raises(ValidationError, match="sys_arg_overrides"):
        ArgSweeper.from_config_file(path, SimpleArgs)
