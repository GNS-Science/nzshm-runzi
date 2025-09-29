from .inversion_solution_builder import InversionSolutionBuilder
from runzi.automation.scaling.toshi_api import ModelType, ToshiApi
import time
import git
import argparse
import json
import urllib.parse
from typing import TYPE_CHECKING, cast
from runzi.runners.inversion_inputs import SubductionInversionArgs, InversionSystemArgs, SubductionTaskArgs

if TYPE_CHECKING:
    from py4j.java_gateway import JavaObject

# TODO: do I need all these casts? 

class SubductionInversionSolutionBuilder(InversionSolutionBuilder):
    """
    A task to build inversion solutions specifically for subduction zones.
    Inherits from InversionBuilderTask and may include additional methods or
    overrides specific to subduction zone characteristics.
    """

    def _get_runner(self) -> 'JavaObject':
        return self._gateway.entry_point.getSubductionInversionRunner()

    def _set_scaling_relationship(self):
        self.user_args = cast(SubductionInversionArgs, self.user_args)
        scaling_relationship = self.user_args.task.scaling_relationship[0]
        scaling_recalc_mag = self.user_args.task.scaling_recalc_mag[0]
        # TODO: would we ever specify a scaling relationship and not want to recalc mags? Isn't that implied?
        # TODO: is it ok not to set a scaling relationship? Does that simply mean we don't relcalc the mags?
        if (scaling_relationship is not None) and scaling_recalc_mag: 
            sr = self._gateway.jvm.nz.cri.gns.NZSHM22.opensha.calc.SimplifiedScalingRelationship()
            if scaling_relationship == "SIMPLE_SUBDUCTION":
                sr.setupSubduction(self.user_args.task.scaling_c_val[0])
            else:
                sr = scaling_relationship  # setScalingRelationship can be passed a string
            self.inversion_runner.setScalingRelationship(sr, scaling_recalc_mag)
    

    def _set_deformation_model(self):
        super()._set_deformation_model()

    def _set_mfd(self):
        self.user_args = cast(SubductionInversionArgs, self.user_args)
        if self.user_args.task.mfd_min_mag[0] is not None:
            self.inversion_runner.setGutenbergRichterMFD(
                self.user_args.task.mfd[0].N,
                self.user_args.task.mfd[0].b,
                self.user_args.task.mfd_eq_ineq_transition_mag[0],
                self.user_args.task.mfd_min_mag[0],
            )
        else:
            self.inversion_runner.setGutenbergRichterMFD(
                self.user_args.task.mfd[0].N, self.user_args.task.mfd[0].b, self.user_args.task.mfd_eq_ineq_transition_mag[0]
            )

    def _domain_specific_setup(self):
        pass


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

    user_args = SubductionInversionArgs(**config['task_args'])
    system_args = InversionSystemArgs(**config['task_system_args'])
    inversion_solution_builder = SubductionInversionSolutionBuilder(user_args, system_args)

    inversion_solution_builder.run()

if __name__ == "__main__":
    main()