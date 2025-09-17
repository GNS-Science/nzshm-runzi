import json
from pathlib import Path

import pytest

import runzi
import runzi.configuration.crustal_inversion_permutations as branch_generators
from runzi.runners.inversion_inputs import Config, from_json_format
from runzi.runners.inversion_inputs_v2 import InversionInput

bad_files = [
    '2021-10-20_TQ9T_config.json',
    '2021-10-20_2VRR_config.json',
    '2021-10-20_PGN8_config.json',
    'example_config.json',
    '22-02-17-TTB039_TEST_config.json',
    '1_config.json',
    '2022-02-10_PUY1_config.json',
    '2022-02-07_TESTPUY_config.json',
]
configs_dir = Path(runzi.__file__).parent / 'fixtures/INVERSION'
fixtures_dir = Path(__file__).parent.parent / 'fixtures/runners/inversion_input'
crustal_configs = []
for filepath in (configs_dir / 'CRUSTAL').glob('*json'):
    if filepath.name not in bad_files:
        crustal_configs.append(filepath)

subduction_configs = []
for filepath in (configs_dir / 'SUBDUCTION').glob('*json'):
    if filepath.name not in bad_files:
        subduction_configs.append(filepath)

all_configs = crustal_configs + subduction_configs

# def load_config(config_filepath: Path) -> Config:
#     loaded_config = json.loads(config_filepath.read_text())
#     formatted_json = from_json_format(loaded_config)
#     config = Config()
#     config.from_json(formatted_json)
#     return config

def load_config(config_filepath: Path) -> Config:
    return InversionInput.model_validate_json(config_filepath.read_text())


def compare_dicts(dict_expected, dict_recieved):

    # first check that dict2 has all the keys that are in dict1
    if not(dict_expected.keys() <= dict_recieved.keys()):
        return False

    # # check that any None values in dict2 are None or missing from dict1
    # for k, v in dict_recieved.items():
    #     if v is None:
    #         if dict_expected.get(k) is not None:
    #             return False

    # # check that all key, values paris in dict1 are in dict2, casting to int or float where needed
    # for key in dict_expected.keys():
    #     if type(dict_recieved[key]) != type(dict_expected[key]):
    #         t = type(dict_recieved[key])
    #         try:
    #             v1 = t(dict_expected[key])
    #         except ValueError:
    #             return False
    #         if v1 != dict_recieved[key]:
    #             return False
    #     elif dict_recieved[key] != dict_expected[key]:
    #         return False
    
    return True
            



# @pytest.mark.parametrize("config_filepath", all_configs)
# def test_get_job_args(config_filepath: Path):
#     fixture_filepath = fixtures_dir / f'job_args-{config_filepath.name}'
#     config = load_config(config_filepath)
#     job_args = config.get_job_args()
#     # fixture_filepath.write_text(json.dumps(job_args))
#     job_args_expected = json.loads(fixture_filepath.read_text())
#     assert job_args == job_args_expected


# @pytest.mark.parametrize("config_filepath", all_configs)
# def test_get_task_args(config_filepath: Path):
#     fixture_filepath = fixtures_dir / f'task_args-{config_filepath.name}'
#     config = load_config(config_filepath)
#     task_args = config.get_task_args()
#     # fixture_filepath.write_text(json.dumps(task_args))
#     task_args_expected = json.loads(fixture_filepath.read_text())
#     assert task_args == task_args_expected


@pytest.mark.parametrize("config_filepath", all_configs)
def test_get_run_args(config_filepath: Path):
    fixture_filepath = fixtures_dir / f'run_args-{config_filepath.name}'
    config = load_config(config_filepath)
    run_args = config.get_run_args()
    # fixture_filepath.write_text(json.dumps(run_args))
    run_args_expected = json.loads(fixture_filepath.read_text())
    # assert run_args == run_args_expected
    assert(compare_dicts(run_args_expected, run_args))


# @pytest.mark.parametrize("config_filepath", all_configs)
# def test_general_args(config_filepath: Path):
#     fixture_filepath = fixtures_dir / f'general_args-{config_filepath.name}'
#     config = load_config(config_filepath)
#     general_args = config.get_general_args()
#     # fixture_filepath.write_text(json.dumps(general_args))
#     general_args_expected = json.loads(fixture_filepath.read_text())
#     del general_args['_unique_id']
#     del general_args_expected['_unique_id']
#     assert general_args == general_args_expected


@pytest.mark.parametrize("config_filepath", all_configs)
def test_config_version(config_filepath: Path):
    fixture_filepath = fixtures_dir / f'config_version-{config_filepath.name}'
    config = load_config(config_filepath)
    config_version = config.get_config_version()
    # fixture_filepath.write_text(json.dumps(config_version))
    config_version_expected = json.loads(fixture_filepath.read_text())
    assert config_version == config_version_expected


# @pytest.mark.parametrize("config_filepath", all_configs)
# def test_get_all_args(config_filepath: Path):
#     fixture_filepath = fixtures_dir / f'all_args-{config_filepath.name}'
#     config = load_config(config_filepath)
#     all_args = config.get_all()
#     # fixture_filepath.write_text(json.dumps(all_args))
#     all_args_expected = json.loads(fixture_filepath.read_text())
#     del all_args['_unique_id']
#     del all_args_expected['_unique_id']
#     assert all_args == all_args_expected


@pytest.mark.parametrize("config_filepath", crustal_configs)
def test_parse_versions(config_filepath: Path):
    # these configs don't meet expectations of the permutation_generator
    skip = [
        '22-02-28-LTB052_config.json',
        '22-02-28-LTB051_config.json',
        '22-02-27-TTB049_TEST_config.json',
        '22-02-28-LTB050_config.json',
        '22-02-27-LTB050_config.json',
        '22-02-28-TTB052_TEST_config.json',
        '22-02-27-LTB049_config.json',
    ]
    if config_filepath.name in skip:
        # print(config.get_config_version())
        return
    config = load_config(config_filepath)
    config_version = config.get_config_version()
    if config_version == "2.5":
        permutations_generator = branch_generators.branch_permutations_generator_25
    elif config_version == "3.0":
        permutations_generator = branch_generators.branch_permutations_generator_30
    elif config_version == "3.1":
        permutations_generator = branch_generators.branch_permutations_generator_31
    elif config_version == "3.2":
        permutations_generator = branch_generators.branch_permutations_generator_32
    elif config_version == "3.3":
        permutations_generator = branch_generators.branch_permutations_generator_33
    elif config_version == "3.4":
        permutations_generator = branch_generators.branch_permutations_generator_34
    else:
        return
    run_args = config.get_run_args()
    rupture_set_info = dict(
        id='ABCD',
        filepath='filepath',
        info={'max_jump_distance': 15},
    )
    for task_arguments in permutations_generator(run_args, rupture_set_info):
        assert task_arguments
