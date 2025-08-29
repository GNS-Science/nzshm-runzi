from pathlib import Path

import pytest

from runzi.automation.runner_inputs import AverageSolutionsInput


def test_input_from_toml():
    input_filepath = Path(__file__).parent.parent.parent / 'fixtures/automation/job_inputs/average_solutions.toml'
    with input_filepath.open() as input_file:
        job_input = AverageSolutionsInput.from_toml(input_file)
    assert job_input


average_solutions_data = {
    'title': 'title',
    'description': 'description',
    'solution_groups': [['ABC', 'DEF'], ['123', '456']],
    'worker_pool_size': 5,
}
class_data = [(AverageSolutionsInput, average_solutions_data)]


@pytest.mark.parametrize("cls,data", class_data)
def test_average_solutions_input(cls, data):
    job_input = cls(**data)
    for k, v in data.items():
        assert getattr(job_input, k) == v
