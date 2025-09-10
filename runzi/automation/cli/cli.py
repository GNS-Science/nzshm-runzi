from pathlib import Path
from typing import Any, Dict, Union

import click
import tomlkit

from runzi.runners.oq_disagg import run_oq_disagg
from runzi.runners.oq_hazard import run_oq_hazard


def load_input(config_filename: Union[Path, str]) -> Dict[str, Any]:
    with Path(config_filename).open('r') as config_file:
        data = config_file.read()
    config = tomlkit.parse(data).unwrap()
    config["filepath"] = Path(config_filename).absolute()
    return config


@click.group()
def rnz_hazard():
    pass


@rnz_hazard.command(name="oq-hazard", help="launch OpenQuake hazard calculation jobs")
@click.argument("config-filename", type=click.Path(exists=True))
def run_oq_hazard_cli(config_filename: str):
    config = load_input(config_filename)
    run_oq_hazard(config)


@rnz_hazard.command(name="oq-disagg", help="launch OpenQuake disagg calculation jobs")
@click.argument("config-filename", type=click.Path(exists=True))
def run_oq_disagg_cli(config_filename: str):
    config = load_input(config_filename)
    run_oq_disagg(config)


# @rnz.command(name="gt-index", help="search or modify the GT index")
# @click.option("--force", default=True)
# def gt_index(force):
#     pass

# @gt_index.command(name="list-ids")
# def list_ids():


if __name__ == "__main__":
    rnz_hazard()  # pragma: no cover
