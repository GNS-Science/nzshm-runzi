import importlib.resources as resources

import pytest
from pydantic import ValidationError

from runzi.automation.openquake.config import DisaggConfig, HazardConfig


# default fixture should be a valid config
def test_config_validation(config_dict):
    HazardConfig.model_validate(config_dict)


def test_config_valid_model_version(config_dict):
    config_dict["hazard_model"]["nshm_model_version"] = "NOT A VERSION"
    with pytest.raises(ValidationError):
        HazardConfig.model_validate(config_dict)


# can specify logic trees using relative path from config file
def test_config_validation_lt_relpath(config_dict):
    config_dict["hazard_model"]["gmcm_logic_tree"] = "gmcm_small.json"
    HazardConfig.model_validate(config_dict)


# can specify logic trees using absolute path from config file
def test_config_validation_lt_abspath(config_dict):
    ref = resources.files('test.fixtures.oq_hazard') / 'gmcm_small.json'
    with resources.as_file(ref) as gmcm_path:
        config_dict["hazard_model"]["gmcm_logic_tree"] = str(gmcm_path.absolute())
    HazardConfig.model_validate(config_dict)


# but the path must exist
def test_config_validation_lt_nopath(config_dict):
    config_dict["hazard_model"]["gmcm_logic_tree"] = "gmcm_not_here.json"
    with pytest.raises(ValidationError):
        HazardConfig.model_validate(config_dict)


# if a model version is not specified, 2 LTs and a hazard config are needed
def test_config_validation_lt_missing(config_dict):
    config_dict["hazard_model"]["gmcm_logic_tree"] = "gmcm_small.json"
    del config_dict["hazard_model"]["nshm_model_version"]
    with pytest.raises(ValidationError):
        HazardConfig.model_validate(config_dict)


# if a model version is not specified, 2 LTs and a hazard config are needed
def test_config_validation_lt_all(config_dict):
    config_dict["hazard_model"]["gmcm_logic_tree"] = "gmcm_small.json"
    config_dict["hazard_model"]["srm_logic_tree"] = "srm_small.json"
    config_dict["hazard_model"]["hazard_config"] = "hazard_config.json"
    del config_dict["hazard_model"]["nshm_model_version"]
    HazardConfig.model_validate(config_dict)


# can specify locations with a file
def test_config_validation_location_file(config_dict):
    del config_dict["site_params"]["locations"]
    config_dict["site_params"]["locations_file"] = "sites.csv"
    HazardConfig.model_validate(config_dict)


# but not both a file and a list
def test_config_validation_location_listandfile(config_dict):
    config_dict["site_params"]["locations_file"] = "sites.csv"
    with pytest.raises(ValidationError):
        HazardConfig.model_validate(config_dict)


# if a uniform vs30 is not provided, the locations file must provide it
def test_config_validation_vs30_missing(config_dict):
    del config_dict["site_params"]["vs30s"]
    with pytest.raises(ValidationError):
        HazardConfig.model_validate(config_dict)


# the vs30s are site specific and in the locations file
def test_config_validation_1(config_dict):
    del config_dict["site_params"]["locations"]
    del config_dict["site_params"]["vs30s"]
    config_dict["site_params"]["locations_file"] = "sites_vs30.csv"
    HazardConfig.model_validate(config_dict)


table_param_value = [
    ("hazard_curve", "imts", "PGA"),
    ("hazard_curve", "imtls", 0.1),
    ("site_params", "vs30s", 100),
    ("site_params", "locations", "WLG"),
]


@pytest.mark.parametrize("table,param,value", table_param_value)
def test_coerse_to_list(config_dict, table, param, value):
    config_dict[table][param] = value
    HazardConfig.model_validate(config_dict)


table_param_value_disagg = [
    ("hazard_curve", "aggs", "mean"),
    ("hazard_curve", "imts", "SA(1.0)"),
    ("disagg", "poes", 0.3),
]


@pytest.mark.parametrize("table,param,value", table_param_value_disagg)
def test_coerse_to_list_disagg(disagg_config_dict, table, param, value):
    disagg_config_dict[table][param] = value
    DisaggConfig.model_validate(disagg_config_dict)


def test_disagg_config_validation(disagg_config_dict):
    DisaggConfig.model_validate(disagg_config_dict)


# the aggs must be present in AggregationEnum
def test_disagg_incorrect_agg(disagg_config_dict):
    disagg_config_dict["hazard_curve"]["aggs"] = ["PGA", "XYZ"]
    with pytest.raises(ValidationError):
        DisaggConfig.model_validate(disagg_config_dict)
