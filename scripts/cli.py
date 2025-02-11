import click
import toml

from typing import Union

from pathlib import Path

from runzi.automation.openquake.run_oq_disagg import run_oq_disagg
from runzi.automation.openquake.run_oq_hazard import run_oq_hazard

def load_config(config_filename: Union[Path, str]):
    config = toml.load(config_filename)
    config["file"] = {"path": str(Path(config_filename).absolute())}
    return config

@click.group()
def rnz():
    pass

@rnz.command(name="oq-hazard", help="launch OpenQuake hazard calculation jobs")
@click.argument("config-filename", type=click.Path(exists=True))
def run_oq_hazard_cli(config_filename: str):
    config = load_config(config_filename)
    run_oq_hazard(config)


@rnz.command(name="oq-disagg", help="launch OpenQuake disagg calculation jobs")
@click.argument("config-filename", type=click.Path(exists=True))
def run_oq_disagg_cli(config_filename: str):
    config = load_config(config_filename)
    run_oq_disagg(config)


# @rnz.command(name="gt-index", help="search or modify the GT index")
# @click.option("--force", default=True)
# def gt_index(force):
#     pass

# @gt_index.command(name="list-ids")
# def list_ids():



if __name__ == "__main__":
    rnz()  # pragma: no cover