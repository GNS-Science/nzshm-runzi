import importlib.resources as resources

import pytest
from pydantic import ValidationError

from runzi.automation.openquake.config import HazardConfig


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
    del config_dict["site_params"]["vs30"]
    with pytest.raises(ValidationError):
        HazardConfig.model_validate(config_dict)


# the vs30s are site specific and in the locations file
def test_config_validation_1(config_dict):
    del config_dict["site_params"]["locations"]
    del config_dict["site_params"]["vs30"]
    config_dict["site_params"]["locations_file"] = "sites_vs30.csv"
    HazardConfig.model_validate(config_dict)
