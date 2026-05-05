import time
from typing import TYPE_CHECKING, Optional, cast

import git

from runzi.arguments import SystemArgs, TaskLanguage
from runzi.automation.local_config import USE_API
from runzi.automation.toshi_api import ModelType
from runzi.tasks.get_config import get_config
from runzi.tasks.inversion.inversion_solution_builder import InversionArgs, InversionSolutionBuilder

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


class SubductionInversionArgs(InversionArgs):
    """Subduction inversion arguments."""

    scaling_c_val: Optional[float] = None
    mfd_min_mag: float


class SubductionInversionSolutionBuilder(InversionSolutionBuilder):
    """
    A task to build inversion solutions specifically for subduction zones.
    Inherits from InversionBuilderTask and may include additional methods or
    overrides specific to subduction zone characteristics.
    """

    def _get_runner(self) -> 'JavaObject':
        return self.gateway.entry_point.getSubductionInversionRunner()

    def _set_scaling_relationship(self):
        self.user_args = cast(SubductionInversionArgs, self.user_args)
        scaling_relationship = self.user_args.scaling_relationship
        scaling_recalc_mag = self.user_args.scaling_recalc_mag
        # TODO: would we ever specify a scaling relationship and not want to recalc mags? Isn't that implied?
        # TODO: is it ok not to set a scaling relationship? Does that simply mean we don't relcalc the mags?
        if (scaling_relationship is not None) and scaling_recalc_mag:
            sr = self.gateway.jvm.nz.cri.gns.NZSHM22.opensha.calc.SimplifiedScalingRelationship()
            if scaling_relationship == "SIMPLE_SUBDUCTION":
                sr.setupSubduction(self.user_args.scaling_c_val)
            else:
                sr = scaling_relationship  # setScalingRelationship can be passed a string
            self.inversion_runner.setScalingRelationship(sr, scaling_recalc_mag)

    def _set_deformation_model(self):
        super()._set_deformation_model()

    def _set_mfd(self):
        self.user_args = cast(SubductionInversionArgs, self.user_args)
        if self.user_args.mfd_min_mag is not None:
            self.inversion_runner.setGutenbergRichterMFD(
                self.user_args.mfd.N,
                self.user_args.mfd.b,
                self.user_args.mfd_eq_ineq_transition_mag,
                self.user_args.mfd_min_mag,
            )
        else:
            self.inversion_runner.setGutenbergRichterMFD(
                self.user_args.mfd.N,
                self.user_args.mfd.b,
                self.user_args.mfd_eq_ineq_transition_mag,
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


if __name__ == "__main__":
    config = get_config()

    # print(config)
    user_args = SubductionInversionArgs(**config['task_args'])
    system_args = SystemArgs(**config['task_system_args'])
    task = SubductionInversionSolutionBuilder(user_args, system_args, ModelType.SUBDUCTION)

    # maybe the JVM App is a little slow to get listening
    time.sleep(3)
    # Wait for some more time, scaled by taskid to avoid S3 consistency issue
    time.sleep(system_args.task_count)

    task.run()
