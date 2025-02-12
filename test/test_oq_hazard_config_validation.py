import importlib.resources as resources

import pytest

from runzi.automation.openquake.run_oq_hazard import validate_config


# default fixture should be a valid config
def test_config_validation(config_dict):
    validate_config(config_dict, 'hazard')


# can specify logic trees using relative path from config file
def test_config_validation_lt_relpath(config_dict):
    config_dict["model"]["gmcm_logic_tree"] = "gmcm_small.json"
    validate_config(config_dict, 'hazard')


# can specify logic trees using absolute path from config file
def test_config_validation_lt_abspath(config_dict):
    with resources.path('test.fixtures.oq_hazard', 'gmcm_small.json') as gmcm_path:
        config_dict["model"]["gmcm_logic_tree"] = str(gmcm_path.absolute())
    validate_config(config_dict, 'hazard')


# but the path must exist
def test_config_validation_lt_nopath(config_dict):
    config_dict["model"]["gmcm_logic_tree"] = "gmcm_not_here.json"
    with pytest.raises(ValueError):
        validate_config(config_dict, 'hazard')


# if a model version is not specified, 2 LTs and a hazard config are needed
def test_config_validation_lt_missing(config_dict):
    config_dict["model"]["gmcm_logic_tree"] = "gmcm_small.json"
    del config_dict["model"]["nshm_model_version"]
    with pytest.raises(ValueError):
        validate_config(config_dict, 'hazard')


# if a model version is not specified, 2 LTs and a hazard config are needed
def test_config_validation_lt_all(config_dict):
    config_dict["model"]["gmcm_logic_tree"] = "gmcm_small.json"
    config_dict["model"]["srm_logic_tree"] = "srm_small.json"
    config_dict["model"]["hazard_config"] = "hazard_config.json"
    del config_dict["model"]["nshm_model_version"]
    validate_config(config_dict, 'hazard')


# can specify locations with a file
def test_config_validation_location_file(config_dict):
    del config_dict["site_params"]["locations"]
    config_dict["site_params"]["locations_file"] = "sites.csv"
    validate_config(config_dict, 'hazard')


# but not both a file and a list
def test_config_validation_location_listandfile(config_dict):
    config_dict["site_params"]["locations_file"] = "sites.csv"
    with pytest.raises(ValueError):
        validate_config(config_dict, 'hazard')


# if a uniform vs30 is not provided, the locations file must provide it
def test_config_validation_vs30_missing(config_dict):
    del config_dict["site_params"]["vs30"]
    with pytest.raises(ValueError):
        validate_config(config_dict, 'hazard')


# the vs30s are site specific and in the locations file
def test_config_validation_1(config_dict):
    del config_dict["site_params"]["locations"]
    del config_dict["site_params"]["vs30"]
    config_dict["site_params"]["locations_file"] = "sites_vs30.csv"
    validate_config(config_dict, 'hazard')
