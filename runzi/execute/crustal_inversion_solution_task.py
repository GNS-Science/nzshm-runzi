import argparse
from zipfile import ZipFile
from runzi.automation.scaling.local_config import WORK_PATH
from pathlib import Path
import json
import urllib.parse
from typing import TYPE_CHECKING, cast

import git

from runzi.execute.inversion_solution_builder import InversionSolutionBuilder
from runzi.runners.inversion_inputs import CrustalInversionArgs
from runzi.runners.runner_inputs import SystemArgs
from runzi.automation.scaling.file_utils import download_files, get_output_file_id

if TYPE_CHECKING:
    from py4j.java_gateway import JavaObject


class CrustalInversionSolutionBuilder(InversionSolutionBuilder):
    """
    A task to build inversion solutions specifically for crustal deformation.
    Inherits from InversionSolutionBuilderTask and may include additional methods or
    overrides specific to crustal characteristics.
    """

    def _get_runner(self) -> 'JavaObject':
        return self._gateway.entry_point.getCrustalInversionRunner()

    def _set_scaling_relationship(self):
        self.user_args = cast(CrustalInversionArgs, self.user_args)
        scaling_relationship = self.user_args.task.scaling_relationship[0]
        scaling_recalc_mag = self.user_args.task.scaling_recalc_mag[0]
        # TODO: would we ever specify a scaling relationship and not want to recalc mags? Isn't that implied?
        # TODO: is it ok not to set a scaling relationship? Does that simply mean we don't relcalc the mags?
        if (scaling_relationship is not None) and scaling_recalc_mag:
            sr = self._gateway.jvm.nz.cri.gns.NZSHM22.opensha.calc.SimplifiedScalingRelationship()
            if scaling_relationship == "SIMPLE_CRUSTAL":
                c_dip = self.user_args.task.scaling_c_val[0].dip
                c_strike = self.user_args.task.scaling_c_val[0].strike
                sr.setupCrustal(c_dip, c_strike)
            else:
                sr = scaling_relationship  # setScalingRelationship can be passed a string
            self.inversion_runner.setScalingRelationship(sr, scaling_recalc_mag)

    def _set_deformation_model(self):
        self.user_args = cast(CrustalInversionArgs, self.user_args)
        super()._set_deformation_model()
        self.inversion_runner.setSlipRateFactor(
            self.user_args.task.slip_rate_factor[0].sans,
            self.user_args.task.slip_rate_factor[0].sans,
        )

    def _set_constraint_weights(self):
        super()._set_constraint_weights()
        reweight = self.user_args.task.reweight[0]
        paleo_rate_constraint_weight = self.user_args.task.paleo_rate_constraint_weight[0]
        paleo_parent_rate_smoothness_constraint_weight = (
            self.user_args.task.paleo_parent_rate_smoothness_constraint_weight[0]
        )
        paleo_rate_constraint = self.user_args.task.paleo_rate_constraint[0]
        paleo_probability_model = self.user_args.task.paleo_probability_model[0]
        paleo_rates_file = self.user_args.task.paleo_rates_file[0]
        if paleo_rate_constraint_weight is not None:
            weight = 1.0 if reweight else paleo_rate_constraint_weight
            self.inversion_runner.setPaleoRateConstraints(
                weight,
                paleo_parent_rate_smoothness_constraint_weight,
                paleo_rate_constraint,
                paleo_probability_model,
            )
        if paleo_rates_file is not None:
            file_generator = get_output_file_id(self._toshi_api, paleo_rates_file.archive_id)
            paleo_file_info = download_files(self._toshi_api, file_generator, str(WORK_PATH), overwrite=False)
            paleo_archive_file_path = paleo_file_info[paleo_rates_file.archive_id]['filepath']
            with ZipFile(paleo_archive_file_path, 'r') as archive:
                archive.extract(paleo_rates_file.file_name, path=Path(paleo_archive_file_path).parent)
            paleo_file_path = Path(paleo_archive_file_path).parent / paleo_rates_file.file_name
            self.inversion_runner.setPaleoRatesFile(str(paleo_file_path))

    def _domain_specific_setup(self):
        if (spatial_seis_pdf := self.user_args.task.spatial_seis_pdf[0]) is not None:
            self.inversion_runner.setSpatialSeisPDF(spatial_seis_pdf)

    def _set_mfd(self):
        self.user_args = cast(CrustalInversionArgs, self.user_args)

        mfd_transition_mag = self.user_args.task.mfd_eq_ineq_transition_mag[0] or 9.0
        self.inversion_runner.setGutenbergRichterMFD(
            self.user_args.task.mfd[0].N,
            self.user_args.task.mfd[0].N_tvz,
            self.user_args.task.mfd[0].b,
            self.user_args.task.mfd[0].b_tvz,
            mfd_transition_mag,
        )

        if self.user_args.task.mfd[0].enable_tvz:
            self.inversion_runner.setEnableTvzMFDs(True)

        self.inversion_runner.setMinMags(
            self.user_args.task.mag_range[0].min_mag_sans, self.user_args.task.mag_range[0].min_mag_tvz
        )
        self.inversion_runner.setMaxMags(
            self.user_args.task.max_mag_type[0],
            self.user_args.task.mag_range[0].max_mag_sans,
            self.user_args.task.mag_range[0].max_mag_tvz,
        )


def get_repo_heads(rootdir, repos):
    result = {}
    for reponame in repos:
        repo = git.Repo(rootdir.joinpath(reponame))
        headcommit = repo.head.commit
        result[reponame] = headcommit.hexsha
    return result


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    args = parser.parse_args()

    try:
        # LOCAL and CLUSTER this is a file
        f = open(args.config, 'r', encoding='utf-8')
        config = json.load(f)
    except FileNotFoundError:
        # for AWS this must be a quoted JSON string
        config = json.loads(urllib.parse.unquote(args.config))

    user_args = CrustalInversionArgs(**config['task_args'])
    system_args = SystemArgs(**config['task_system_args'])
    inversion_solution_builder = CrustalInversionSolutionBuilder(user_args, system_args)

    inversion_solution_builder.run()


if __name__ == "__main__":
    main()
