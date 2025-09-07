from pathlib import Path

import pytest
import tomlkit

import runzi.automation.runner_inputs as runner_inputs
from pydantic import ValidationError

fixtures_path = Path(__file__).parent.parent.parent / 'fixtures/automation/job_inputs'


def get_dict_from_toml(filepath):
    toml_str = Path(filepath).read_text()
    return tomlkit.parse(toml_str).unwrap()


def test_input_from_toml_io():
    input_filepath = fixtures_path / 'average_solutions.toml'
    with input_filepath.open() as input_file:
        job_input = runner_inputs.AverageSolutionsInput.from_toml(input_file)
    assert job_input


class_filename = [
    (runner_inputs.AverageSolutionsInput, 'average_solutions.toml'),
    (runner_inputs.AzimuthalRuptureSetsInput, 'azimuthal_rupture_sets.toml'),
    (runner_inputs.CoulombRuptureSetsInput, 'coulomb_rupture_sets.toml'),
    (runner_inputs.ScaleSolutionsInput, 'scale_solutions.toml'),
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
        assert runner_inputs.ScaleSolutionsInput(**data)
    for data in [data1, data2]:
        with pytest.raises(ValidationError):
            runner_inputs.ScaleSolutionsInput(**data)