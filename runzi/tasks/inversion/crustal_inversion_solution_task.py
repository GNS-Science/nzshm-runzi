import argparse
import json
import time
import urllib.parse
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Self, cast
from zipfile import ZipFile

import git
from pydantic import BaseModel, model_validator

from runzi.arguments import SystemArgs, TaskLanguage
from runzi.automation.file_utils import download_files, get_output_file_id
from runzi.automation.local_config import USE_API, WORK_PATH
from runzi.automation.toshi_api import ModelType
from runzi.tasks.inversion.inversion_solution_builder import InversionArgs, InversionSolutionBuilder, all_or_none

if TYPE_CHECKING:
    from py4j.java_gateway import JavaObject

default_system_args = SystemArgs(
    task_language=TaskLanguage.JAVA,
    use_api=USE_API,
    # java_threads is only used for pbs mode, which is not supported anymore.
    # It should be set to selector_threads * averaging_threads, but this would need to be done task by task if they
    # are swept args. It would be possible to add some inversion specific code to the build_tasks function or find the
    # maximum number of threads before hand or find the maximum number of threads that would be needed before hand.
    java_threads=16,
    jvm_heap_max=32,
    ecs_max_job_time_min=60,
    ecs_memory=30720,
    ecs_vcpu=4,
    ecs_job_definition="Fargate-runzi-opensha-JD",
    ecs_job_queue="BasicFargate_Q",
)


class CrustalInversionArgs(InversionArgs):
    class ScalingC(BaseModel):
        dip: float
        strike: float
        tag: str

    class MagRange(BaseModel):
        min_mag_sans: float
        max_mag_sans: float
        min_mag_tvz: float
        max_mag_tvz: float

    class SlipRateFactor(BaseModel):
        tag: str
        sans: float
        tvz: float

    class PaleoRatesFile(BaseModel):
        archive_id: str
        file_name: str
        tag: str

    spatial_seis_pdf: Optional[str] = None

    scaling_c_val: Optional[ScalingC] = None

    max_mag_type: str
    mag_range: MagRange

    slip_rate_factor: SlipRateFactor

    paleo_rate_constraint_weight: Optional[float] = None
    paleo_parent_rate_smoothness_constraint_weight: Optional[float] = None
    paleo_rate_constraint: Optional[str] = None
    paleo_probability_model: Optional[str] = None
    paleo_rates_file: Optional[PaleoRatesFile] = None

    @model_validator(mode='after')
    def _check_paleo_constraint(self) -> Self:
        """If using paleo constraint, must specify all parameters."""
        params = [
            self.paleo_rate_constraint_weight,
            self.paleo_parent_rate_smoothness_constraint_weight,
            self.paleo_rate_constraint,
            self.paleo_probability_model,
        ]
        if not all_or_none(params):
            raise ValueError(
                "If using paleo constraints, must set all parameters (weight, smoothness weight, "
                "constrant enum, probability model)"
            )
        return self


class CrustalInversionSolutionBuilder(InversionSolutionBuilder):
    """
    A task to build inversion solutions specifically for crustal deformation.
    Inherits from InversionSolutionBuilderTask and may include additional methods or
    overrides specific to crustal characteristics.
    """

    def _get_runner(self) -> 'JavaObject':
        return self.gateway.entry_point.getCrustalInversionRunner()

    def _set_scaling_relationship(self):
        self.user_args = cast(CrustalInversionArgs, self.user_args)
        scaling_relationship = self.user_args.scaling_relationship
        scaling_recalc_mag = self.user_args.scaling_recalc_mag
        # TODO: would we ever specify a scaling relationship and not want to recalc mags? Isn't that implied?
        # TODO: is it ok not to set a scaling relationship? Does that simply mean we don't relcalc the mags?
        if (scaling_relationship is not None) and scaling_recalc_mag:
            sr = self.gateway.jvm.nz.cri.gns.NZSHM22.opensha.calc.SimplifiedScalingRelationship()
            if scaling_relationship == "SIMPLE_CRUSTAL":
                c_dip = self.user_args.scaling_c_val.dip
                c_strike = self.user_args.scaling_c_val.strike
                sr.setupCrustal(c_dip, c_strike)
            else:
                sr = scaling_relationship  # setScalingRelationship can be passed a string
            self.inversion_runner.setScalingRelationship(sr, scaling_recalc_mag)

    def _set_deformation_model(self):
        self.user_args = cast(CrustalInversionArgs, self.user_args)
        super()._set_deformation_model()
        self.inversion_runner.setSlipRateFactor(
            self.user_args.slip_rate_factor.sans,
            self.user_args.slip_rate_factor.sans,
        )

    def _set_constraint_weights(self):
        super()._set_constraint_weights()
        reweight = self.user_args.reweight
        paleo_rate_constraint_weight = self.user_args.paleo_rate_constraint_weight
        paleo_parent_rate_smoothness_constraint_weight = self.user_args.paleo_parent_rate_smoothness_constraint_weight
        paleo_rate_constraint = self.user_args.paleo_rate_constraint
        paleo_probability_model = self.user_args.paleo_probability_model
        paleo_rates_file = self.user_args.paleo_rates_file
        if paleo_rate_constraint_weight is not None:
            weight = 1.0 if reweight else paleo_rate_constraint_weight
            self.inversion_runner.setPaleoRateConstraints(
                weight,
                paleo_parent_rate_smoothness_constraint_weight,
                paleo_rate_constraint,
                paleo_probability_model,
            )
        if paleo_rates_file is not None:
            file_generator = get_output_file_id(self.toshi_api, paleo_rates_file.archive_id)
            paleo_file_info = download_files(self.toshi_api, file_generator, str(WORK_PATH), overwrite=False)
            paleo_archive_file_path = paleo_file_info[paleo_rates_file.archive_id]['filepath']
            with ZipFile(paleo_archive_file_path, 'r') as archive:
                archive.extract(paleo_rates_file.file_name, path=Path(paleo_archive_file_path).parent)
            paleo_file_path = Path(paleo_archive_file_path).parent / paleo_rates_file.file_name
            self.inversion_runner.setPaleoRatesFile(str(paleo_file_path))

    def _domain_specific_setup(self):
        if (spatial_seis_pdf := self.user_args.spatial_seis_pdf) is not None:
            self.inversion_runner.setSpatialSeisPDF(spatial_seis_pdf)

    def _set_mfd(self):
        self.user_args = cast(CrustalInversionArgs, self.user_args)

        mfd_transition_mag = self.user_args.mfd_eq_ineq_transition_mag or 9.0
        self.inversion_runner.setGutenbergRichterMFD(
            self.user_args.mfd.N,
            self.user_args.mfd.N_tvz,
            self.user_args.mfd.b,
            self.user_args.mfd.b_tvz,
            mfd_transition_mag,
        )

        if self.user_args.mfd.enable_tvz:
            self.inversion_runner.setEnableTvzMFDs(True)

        self.inversion_runner.setMinMags(self.user_args.mag_range.min_mag_sans, self.user_args.mag_range.min_mag_tvz)
        self.inversion_runner.setMaxMags(
            self.user_args.max_mag_type,
            self.user_args.mag_range.max_mag_sans,
            self.user_args.mag_range.max_mag_tvz,
        )


def get_repo_heads(rootdir, repos):
    result = {}
    for reponame in repos:
        repo = git.Repo(rootdir.joinpath(reponame))
        headcommit = repo.head.commit
        result[reponame] = headcommit.hexsha
    return result


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    args = parser.parse_args()

    try:
        # LOCAL and CLUSTER this is a file
        config_file = args.config
        f = open(args.config, 'r', encoding='utf-8')
        config = json.load(f)
    except FileNotFoundError:
        # for AWS this must be a quoted JSON string
        config = json.loads(urllib.parse.unquote(args.config))

    # print(config)
    user_args = CrustalInversionArgs(**config['task_args'])
    system_args = SystemArgs(**config['task_system_args'])
    task = CrustalInversionSolutionBuilder(user_args, system_args, ModelType.CRUSTAL)

    # maybe the JVM App is a little slow to get listening
    time.sleep(3)
    # Wait for some more time, scaled by taskid to avoid S3 consistency issue
    time.sleep(system_args.task_count)

    task.run()
