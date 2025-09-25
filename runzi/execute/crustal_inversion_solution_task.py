from .inversion_solution_builder import InversionSolutionBuilder
from runzi.automation.scaling.toshi_api import ModelType, ToshiApi
import time
import git
import argparse
from typing import cast
import json
import urllib.parse
from runzi.runners.inversion_inputs_v2 import InversionArgs, InversionSystemArgs, CrustalInversionArgs


class CrustalInversionSolutionBuilder(InversionSolutionBuilder):
    """
    A task to build inversion solutions specifically for crustal deformation.
    Inherits from InversionSolutionBuilderTask and may include additional methods or
    overrides specific to crustal characteristics.
    """

    def _set_scaling_relationship(self):
        scaling_relationship = self.user_args.task.scaling_relationship[0]
        scaling_recalc_mag = self.user_args.task.scaling_recalc_mags[0]
        # TODO: would we ever specify a scaling relationship and not want to recalc mags? Isn't that implied?
        # TODO: is it ok not to set a scaling relationship? Does that simply mean we don't relcalc the mags?
        if (scaling_relationship is not None) and scaling_recalc_mag: 
            sr = self._gateway.jvm.nz.cri.gns.NZSHM22.opensha.calc.SimplifiedScalingRelationship()
            if scaling_relationship == "SIMPLE_CRUSTAL":
                c_dip = self.user_args.task.scaling_c_vals[0].dip
                c_strike = self.user_args.task.scaling_c_vals[0].strike
                sr.setupCrustal(c_dip, c_strike)
            else:
                sr = scaling_relationship  # setScalingRelationship can be passed a string
            self.inversion_runner.setScalingRelationship(sr, scaling_recalc_mag)

    def _setup_runner(self):
        self.user_args = cast(CrustalInversionArgs, self.user_args)
        self.inversion_runner = self._gateway.entry_point.getCrustalInversionRunner()

        if (spatial_seis_pdf := self.user_args.task.spatial_seis_pdfs[0]) is not None:
            self.inversion_runner.setSpatialSeisPDF(spatial_seis_pdf)

        self.inversion_runner.setDeformationModel(self.user_args.task.deformation_models[0])
        self.inversion_runner.setGutenbergRichterMFD(
            self.user_args.task.mfds[0].N,
            self.user_args.task.mfds[0].N_tvz,
            self.user_args.task.mfds[0].b,
            self.user_args.task.mfds[0].b_tvz,
            self.user_args.task.mfd_transition_mags[0],
        )

        mfd_equality_weight = self.user_args.task.mfd_equality_weights[0]
        mfd_inequality_weight = self.user_args.task.mfd_inequality_weights[0]
        mfd_uncertainty_weight = self.user_args.task.mfd_uncertainty_weights[0]
        mfd_uncertainty_power = self.user_args.task.mfd_uncertainty_powers[0]
        mfd_uncertainty_scalar = self.user_args.task.mfd_uncertainty_scalars[0]
        reweight = self.user_args.task.reweights[0]
        if (mfd_equality_weight is not None) and (mfd_inequality_weight is not None):
            self.inversion_runner.setGutenbergRichterMFDWeights(mfd_equality_weight, mfd_inequality_weight)
        elif ((mfd_uncertainty_weight is not None) and (mfd_uncertainty_power is not None)) or (reweight):
            weight = 1.0 if reweight else mfd_uncertainty_weight
            self.inversion_runner.setUncertaintyWeightedMFDWeights(
                weight, mfd_uncertainty_power, mfd_uncertainty_scalar
            )
        else:
            raise ValueError("Neither eq/ineq , nor uncertainty weights provided for MFD constraint setup")

        if self.user_args.task.mfds[0].enable_tvz:
            self.inversion_runner.setEnableTvzMFDs(True)

        self.inversion_runner.setMinMags(self.user_args.task.min_mag_sans[0], self.user_args.task.min_mag_tvz[0])
        self.inversion_runner.setMaxMags(
            self.user_args.task.max_mag_types[0],
            self.user_args.task.mag_ranges[0].max_mag_sans,
            self.user_args.task.mag_ranges[0].max_mag_tvz,
        )

        self.inversion_runner.setSlipRateFactor(
            self.user_args.task.slip_rate_factors[0].sans,
            self.user_args.task.slip_rate_factors[0].sans,
        )

        if reweight:
            self.inversion_runner.setReweightTargetQuantity("MAD")

        use_slip_scalings = self.user_args.task.use_slip_scalings[0]
        slip_rate_weighting_type = self.user_args.task.slip_rate_weighting_types[0]
        slip_rate_normalized_weight = self.user_args.task.slip_rate_normalized_weights[0]
        slip_rate_unnormalized_weight = self.user_args.task.slip_rate_unnormalized_weights[0]
        if use_slip_scalings is not None:
            # V3x config
            weight = 1.0 if reweight else self.user_args.task.slip_uncertainty_weights[0]
            self.inversion_runner.setSlipRateUncertaintyConstraint(
                weight, self.user_args.task.slip_uncertainty_scaling_factors[0]
            ).setUnmodifiedSlipRateStdvs(
                not use_slip_scalings
            )  # True means no slips scaling and vice-versa
        elif (slip_rate_weighting_type is not None) and slip_rate_weighting_type == 'UNCERTAINTY_ADJUSTED':
            # Deprecated...
            self.inversion_runner.setSlipRateUncertaintyConstraint(
                self.user_args.task.slip_rate_weights[0], self.user_args.task.slip_uncertainty_scaling_factors[0]
            )
        elif slip_rate_normalized_weight is not None:
            # covers UCERF3 style SR constraints
            self.inversion_runner.setSlipRateConstraint(
                slip_rate_weighting_type, slip_rate_normalized_weight, slip_rate_unnormalized_weight
            )
        else:
            raise ValueError("invalid slip constraint weight setup")

        paleo_rate_constraint_weight = self.user_args.task.paleo_rate_constraint_weights[0]
        paleo_parent_rate_smoothness_constraint_weight = (
            self.user_args.task.paleo_parent_rate_smoothness_constraint_weights[0]
        )
        paleo_rate_constraint = self.user_args.task.paleo_rate_constraints[0]
        paleo_probability_model = self.user_args.task.paleo_probability_models[0]
        if paleo_rate_constraint_weight is not None:
            weight = 1.0 if reweight else paleo_rate_constraint_weight
            self.inversion_runner.setPaleoRateConstraints(
                weight,
                weight,
                paleo_parent_rate_smoothness_constraint_weight,
                paleo_rate_constraint,
                paleo_probability_model,
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


    user_args = InversionArgs(**config['task_args'])
    system_args = InversionSystemArgs(**config['task_system_args'])
    inversion_solution_builder = CrustalInversionSolutionBuilder(user_args, system_args)

    inversion_solution_builder.run()

if __name__ == "__main__":
    main()