from .inversion_solution_builder import InversionSolutionBuilder
from runzi.automation.scaling.toshi_api import ModelType, ToshiApi
import time
import git
import argparse
import json
import urllib.parse
from runzi.runners.inversion_inputs_v2 import InversionArgs, InversionSystemArgs


class SubductionInversionSolutionBuilderTask(InversionSolutionBuilder):
    """
    A task to build inversion solutions specifically for subduction zones.
    Inherits from InversionBuilderTask and may include additional methods or
    overrides specific to subduction zone characteristics.
    """


    def setup_runner(self):
        self.inversion_runner = self._gateway.entry_point.getSubductionInversionRunner()
        self.inversion_runner.setDeformationModel(self.user_args.task.deformation_models[0])
        self.inversion_runner.setGutenbergRichterMFDWeights(
            self.user_args.task.mfd_equality_weights[0], self.user_args.task.mfd_inequality_weights[0]
        ).setSlipRateConstraint(
            self.user_args.task.slip_rate_weighting_types[0],
            self.user_args.task.slip_rate_normalized_weights[0],
            self.user_args.task.slip_rate_unnormalized_weights[0],
        )
        if self.user_args.task.mfd_min_mags[0] is not None:
            self.inversion_runner.setGutenbergRichterMFD(
                self.user_args.task.mfds[0].N,
                self.user_args.task.mfds[0].b,
                self.user_args.task.mfd_transition_mags[0],
                self.user_args.task.mfd_min_mags[0],
            )
        else:
            self.inversion_runner.setGutenbergRichterMFD(
                self.user_args.task.mfds[0].N, self.user_args.task.mfds[0].b, self.user_args.task.mfd_transition_mags[0]
            )

        if self.user_args.task.mfd_uncertainty_weights[0] is not None:
            self.inversion_runner.setUncertaintyWeightedMFDWeights(
                self.user_args.task.mfd_uncertainty_weights[0],
                self.user_args.task.mfd_uncertainty_powers[0],
                self.user_args.task.mfd_uncertainty_scalars[0],
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
    inversion_solution_builder = InversionSolutionBuilder(user_args, system_args)

    inversion_solution_builder.run()

if __name__ == "__main__":
    main()