import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, TypeAlias

Config: TypeAlias = Dict[str, Dict[str, Any]]


def validate_entry(
    config: Config,
    table: str,
    name: str,
    types: Iterable[type],
    subtype: Optional[type] = None,
    optional: Optional[bool] = False,
    choice: Optional[List[Any]] = None,
):
    """
    Validate a config variable.
    Every entry in a config is assumed to be under a table, i.e. config is type Dict[str, Dict[Any]]

    Args:
        config: the configuration
        table: the table name for the variable
        name: the name of the variable
        tyes: the list of possible types the variable is allowed to be
        subtype: if the varible is a list, the type of the elements of the list
        optional: true if the variable is not required
        choice: list of possible values the variable is allowed to take

    Raises:
        ValueError: if variable is not valid
    """

    if not optional:
        if not config[table].get(name):
            msg = f"config missing required entry: {name}"
            raise ValueError(msg)

    if optional and not config[table].get(name):
        return

    entry = config[table][name]

    if not isinstance(entry, tuple(types)):
        msg = f"{table, name} must be type in {types}"
        raise ValueError(msg)

    if isinstance(entry, list):
        if len(entry) < 1:
            msg = f"{name} must be list with length > 0"
            raise ValueError(msg)
        if not all(isinstance(x, subtype) for x in entry):
            msg = f"all elements of {name} must be type {subtype}"
            raise ValueError(msg)

    if choice and (entry not in choice):
        msg = f"{name} must be one of {choice}"
        raise ValueError(msg)


def validate_path(config: Config, table: str, name: str):
    """
    Validate a path variable in a configuration and store as absolute path. If the path is not
    aboslute, it will be resolved relative to the path of the config file.

    Args:
        config: the configuration dict
        table: the name of the table where the variable is stored
        name: the name of the path variable

    Raises:
        ValueError: if path does not exist
    """
    validate_entry(config, table, name, [str])
    path = Path(config[table][name])
    if not path.is_absolute():
        path = Path(config["path"]).parent / path
    if not path.exists():
        msg = f"logic tree file {config[table][name]} does not exist"
        raise ValueError(msg)
    config[table][name] = str(path)


def load_logic_tree(file_path):
    spec = importlib.util.spec_from_file_location("logic_tree", file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["logic_tree"] = module
    spec.loader.exec_module(module)

    return module
