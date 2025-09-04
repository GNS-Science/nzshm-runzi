from pathlib import Path

import pytest
import tomlkit

import runzi.automation.runner_inputs as runner_inputs

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
]
@pytest.mark.parametrize("cls,filename", class_filename)
def test_input_class(cls, filename):
    input_filepath = fixtures_path / filename
    data = get_dict_from_toml(input_filepath)
    job_input = cls.from_toml(input_filepath)
    job_input_asdict = job_input.model_dump()
    for k, v in data.items():
        assert job_input_asdict[k] == v
