"""Tests that a general task and its subtasks serialize arguments identically.

Downstream consumers match a subtask's recorded arguments against the argument list of the
general task that spawned it, so both sides must render the same value as the same string.
"""

import datetime as dt
import json
from enum import Enum
from pathlib import Path

import pytest
from pydantic import BaseModel

from runzi.arguments import ArgSweeper, serialize_arguments
from runzi.tasks.inversion import (
    CrustalInversionArgs,
    CrustalInversionJobRunner,
    SubductionInversionArgs,
    SubductionInversionJobRunner,
)
from runzi.tasks.oq_hazard import OQDisaggArgs, OQDisaggJobRunner, OQHazardArgs, OQHazardJobRunner

FIXTURES = Path(__file__).parent / "fixtures"


class Aggregate(Enum):
    MEAN = 'mean'


class RuptureSet(BaseModel):
    rupture_set_id: str
    tag: str


class SampleArgs(BaseModel):
    rupture_set: RuptureSet
    agg: Aggregate
    created: dt.datetime
    reweight: bool


@pytest.fixture(autouse=True)
def no_api(monkeypatch):
    """Keep _build_argument_list off the network (the OQ runners upload logic tree files)."""
    monkeypatch.setattr("runzi.tasks.oq_hazard.oq_hazard_runner.USE_API", False)
    monkeypatch.setattr("runzi.tasks.oq_hazard.oq_disagg_runner.USE_API", False)


def _sample_args(**overrides) -> SampleArgs:
    data = {
        "rupture_set": {"rupture_set_id": "RmlsZTox", "tag": "a tag"},
        "agg": "mean",
        "created": "2026-08-05T12:00:00",
        "reweight": True,
    }
    return SampleArgs.model_validate(data | overrides)


def test_serialize_arguments_normalizes_nested_key_order():
    """A dict argument serializes in field order, whatever order the config file wrote it in."""
    config_order = {"tag": "a tag", "rupture_set_id": "RmlsZTox"}  # reverse of RuptureSet's fields
    assert serialize_arguments(_sample_args(rupture_set=config_order)) == serialize_arguments(_sample_args())


def test_serialize_arguments_uses_json_form():
    """Enums and datetimes render as their JSON value.

    A python-mode dump would give 'Aggregate.MEAN' and a space-separated datetime instead.
    Paths are not covered here: str() of a Path is already the plain path, so both dump modes
    agree and there is nothing to pin down.
    """
    serialized = serialize_arguments(_sample_args())
    assert serialized["agg"] == "mean"
    assert serialized["created"] == "2026-08-05T12:00:00"
    assert serialized["rupture_set"] == "{'rupture_set_id': 'RmlsZTox', 'tag': 'a tag'}"


def test_serialize_arguments_excludes_named_fields():
    serialized = serialize_arguments(_sample_args(), exclude={"agg", "created"})
    assert set(serialized) == {"rupture_set", "reweight"}


def test_serialize_arguments_avoids_double_quotes():
    """kvl_to_graphql interpolates these values into a GraphQL query without escaping."""
    assert '"' not in serialize_arguments(_sample_args())["rupture_set"]


def test_general_task_lists_swept_dict_arg_as_subtasks_report_it(tmp_path):
    """The reported bug: a swept dict written in config order didn't match the subtask's dump."""
    config = json.loads((FIXTURES / "crustal_inversion.json").read_text())
    del config["rupture_set"]
    config["swept_args"] = {
        # keys deliberately in the opposite order to InversionArgs.RuptureSet's field order
        "rupture_set": [
            {"tag": "first rupture set", "rupture_set_id": "RmlsZTox"},
            {"tag": "second rupture set", "rupture_set_id": "RmlsZToy"},
        ]
    }
    config_file = tmp_path / "crustal_inversion.json"
    config_file.write_text(json.dumps(config))

    runner = CrustalInversionJobRunner(ArgSweeper.from_config_file(config_file, CrustalInversionArgs))
    argument_list = {entry["k"]: entry["v"] for entry in runner._build_argument_list()}

    assert argument_list["rupture_set"] == [
        "{'rupture_set_id': 'RmlsZTox', 'tag': 'first rupture set'}",
        "{'rupture_set_id': 'RmlsZToy', 'tag': 'second rupture set'}",
    ]
    for task_args in runner.argument_sweeper.get_tasks():
        assert serialize_arguments(task_args)["rupture_set"] in argument_list["rupture_set"]


@pytest.mark.parametrize(
    "fixture,args_class,runner_class",
    [
        ("crustal_inversion.json", CrustalInversionArgs, CrustalInversionJobRunner),
        ("subduction_inversion.json", SubductionInversionArgs, SubductionInversionJobRunner),
        ("hazard_job.json", OQHazardArgs, OQHazardJobRunner),
        ("disagg_job.json", OQDisaggArgs, OQDisaggJobRunner),
    ],
)
def test_every_subtask_argument_appears_in_general_task_list(fixture, args_class, runner_class):
    """Every value a subtask will record is present, verbatim, in the general task's list."""
    runner = runner_class(ArgSweeper.from_config_file(FIXTURES / fixture, args_class))
    argument_list = {entry["k"]: entry["v"] for entry in runner._build_argument_list()}

    tasks = list(runner.argument_sweeper.get_tasks())
    assert tasks, "fixture generated no tasks"
    for task_args in tasks:
        for name, value in serialize_arguments(task_args).items():
            assert value in argument_list[name], f"subtask value for '{name}' missing from general task list"
