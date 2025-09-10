from pathlib import Path

import pytest
import tomlkit

from runzi.runners import AverageSolutionsInput, CoulombRuptureSetsInput, ScaleSolutionsInput, SubductionRuptureSetsInput, TimeDependentSolutionInput
from pydantic import ValidationError
from runzi.automation.scaling.toshi_api.general_task import ModelType

fixtures_path = Path(__file__).parent.parent / 'fixtures/runners'

@pytest.fixture(scope='function')
def td_data():
    return dict(
        description="Crustal. Geodetic. TD. From LTB89. Final",
        title="Crustal. Geodetic. TD. From LTB98. 100yr. NZ-SHM22 aperiodicity",
        solution_ids=["R2VuZXJhbFRhc2s6NjUzOTY1OQ=="],
        current_years=[2022],
        mre_enums=["CFM_1_1"],
        forecast_timespans=[100],
        aperiodicities=["NZSHM22"],
    )


def get_dict_from_toml(filepath):
    toml_str = Path(filepath).read_text()
    return tomlkit.parse(toml_str).unwrap()


def test_input_from_toml_io():
    input_filepath = fixtures_path / 'average_solutions.toml'
    with input_filepath.open() as input_file:
        job_input = AverageSolutionsInput.from_toml(input_file)
    assert job_input


class_filename = [
    (AverageSolutionsInput, 'average_solutions.toml'),
    (CoulombRuptureSetsInput, 'coulomb_rupture_sets.toml'),
    (ScaleSolutionsInput, 'scale_solutions.toml'),
    (SubductionRuptureSetsInput, 'subduction_rupture_sets.toml'),
    (TimeDependentSolutionInput, 'time_dependent_solution.toml'),
]


@pytest.mark.parametrize("cls,filename", class_filename)
def test_input_class(cls, filename):
    input_filepath = fixtures_path / filename
    data = get_dict_from_toml(input_filepath)
    job_input = cls.from_toml(input_filepath)
    job_input_asdict = job_input.model_dump()
    for k, v in data.items():
        assert job_input_asdict[k] == v

def test_scale_solutions_xor():
    """ScaleSolutionsInput expects both polygon_scale and polygon_max_mag or neither."""
    data0 = dict(
        title="Scaling Crustal (geodetic slip, TD)",
        description= "Scale Crustal by 0.66, 1.0, 1.41",
        solution_ids=["R2VuZXJhbFRhc2s6NjUzOTY5Ng=="],
        scales=[0.66, 1.0, 1.41],
        polygon_scale=0.8,
        polygon_max_mag=8,
    )
    data1, data2, data3 = data0.copy(), data0.copy(), data0.copy()
    del data1['polygon_scale']
    del data2['polygon_max_mag']
    del data3['polygon_scale']
    del data3['polygon_max_mag']

    for data in [data0, data3]:
        assert ScaleSolutionsInput(**data)
    for data in [data1, data2]:
        with pytest.raises(ValidationError):
            ScaleSolutionsInput(**data)

@pytest.mark.parametrize("model_type", [ModelType(10), 20, "CRUSTAL", "subduction", "SuBdUcTiOn"])
def test_time_dependent_model_type(model_type, td_data):
    """model_type can be anything that can be evaluted to ModelType enum."""
    td_data["model_type"] = model_type
    assert TimeDependentSolutionInput(**td_data)


def test_time_dependent_error(td_data):
    """model_type must be able to be evaluted to ModelType enum."""
    td_data["model_type"] = "foobar"
    with pytest.raises(ValidationError):
        assert TimeDependentSolutionInput(**td_data)

def test_time_dependent_serialize(td_data):
    """model_type should be serialzed as name of enum."""
    model_type = ModelType["CRUSTAL"]
    td_data["model_type"] = model_type
    data_dump = TimeDependentSolutionInput(**td_data).model_dump()
    assert data_dump["model_type"] == model_type.name