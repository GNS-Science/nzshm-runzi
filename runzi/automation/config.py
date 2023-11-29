import importlib.util
import sys

from pathlib import Path

def validate_entry(config, name, type, elm_type=None, optional=False, choice=None):

    if not optional:
        if not config.get(name):
            msg = f"config missing required entry: {name}"
            raise ValueError(msg)

    if optional and not config.get(name):
        return 

    entry = config[name]

    if not isinstance(entry, type):
        msg = f"{name} must be type {type}"
        raise ValueError(msg)
    if type is list:
        if len(entry)<1:
            msg = f"{name} must be list with length > 0"
            raise ValueError(msg)
        if not all(isinstance(x,elm_type) for x in entry):
            msg = f"all elements of {name} must be type {elm_type}"
            raise ValueError(msg)
    
    if choice and (config[name] not in choice):
        msg = f"{name} must be one of {choice}"
        raise ValueError(msg)

def validate_path(config, name):
    validate_entry(config, name, str)
    if not Path(config[name]).exists():
        msg = f"logic tree file {config[name]} does not exist"
        raise ValueError(msg)
    

def load_logic_tree(file_path):
    spec = importlib.util.spec_from_file_location("logic_tree", file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["logic_tree"] = module
    spec.loader.exec_module(module)

    return module