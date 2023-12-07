import importlib.util
import sys

from pathlib import Path

def validate_entry(config, table, name, types, elm_type=None, optional=False, choice=None):

    if not optional:
        if not config[table].get(name):
            msg = f"config missing required entry: {name}"
            raise ValueError(msg)

    if optional and not config[table].get(name):
        return 

    entry = config[table][name]

    correct_type = False
    for tpe in types:
        if isinstance(entry, tpe):
            correct_type = True
            break
    if not correct_type:
        msg = f"{table, name} must be type in {types}"
        raise ValueError(msg)

    if isinstance(entry, list):
        if len(entry)<1:
            msg = f"{name} must be list with length > 0"
            raise ValueError(msg)
        if not all(isinstance(x,elm_type) for x in entry):
            msg = f"all elements of {name} must be type {elm_type}"
            raise ValueError(msg)
    
    if choice and (entry not in choice):
        msg = f"{name} must be one of {choice}"
        raise ValueError(msg)

def validate_path(config, table, name):
    validate_entry(config, table, name, [str])
    if not Path(config[table][name]).exists():
        msg = f"logic tree file {config[table][name]} does not exist"
        raise ValueError(msg)
    

def load_logic_tree(file_path):
    spec = importlib.util.spec_from_file_location("logic_tree", file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["logic_tree"] = module
    spec.loader.exec_module(module)

    return module