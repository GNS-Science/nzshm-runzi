from pathlib import Path

import typer

from runzi.runners import (
    CoulombRuptureSetsInput,
    SubductionRuptureSetsInput,
    run_coulomb_rupture_sets,
    run_subduction_rupture_sets,
)

app = typer.Typer()


@app.command()
def coulomb_rupset(input_filepath: Path):
    """Create Coulomb (crustal) rupture sets."""
    job_input = CoulombRuptureSetsInput.from_toml(input_filepath)
    run_coulomb_rupture_sets(job_input)


@app.command()
def sub_rupset(input_filepath: Path):
    """Create subduction rupture sets."""
    job_input = SubductionRuptureSetsInput.from_toml(input_filepath)
    run_subduction_rupture_sets(job_input)
