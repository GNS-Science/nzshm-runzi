from pathlib import Path

import pytest

from runzi.automation.runner_inputs import AverageSolutionsInput, AzimuthalRuptureSetsInput


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
azimuthal_rupture_sets_data = dict(
    title = 'title',
    description =  'description',
    models = ["CFM_0_9_SANSTVZ_2010", "CFM_0_9_SANSTVZ_D90"],
    strategies = ['UCERF3',],
    jump_limits = [ 5.0, ],
    ddw_ratios = [ 0.5, ],
    min_sub_sects_per_parents = [ 2, ]  ,
    min_sub_sections_list = [3, 4, 5],
    max_cumulative_azimuths = [ 560.0, ],
    thinning_factors = [0.0, 0.1] ,
    scaling_relations = [ 'TMG_CRU_2017', ],
    max_sections = 200,
)
class_data = [
    (AverageSolutionsInput, average_solutions_data),
    (AzimuthalRuptureSetsInput, azimuthal_rupture_sets_data),
]
@pytest.mark.parametrize("cls,data", class_data)
def test_average_solutions_input(cls, data):
    job_input = cls(**data)
    for k, v in data.items():
        assert getattr(job_input, k) == v
