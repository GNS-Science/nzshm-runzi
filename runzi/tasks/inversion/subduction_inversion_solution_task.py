import time
from typing import TYPE_CHECKING, cast

import git

from runzi.arguments import SubmissionArgs, TaskLanguage, TaskRuntimeArgs
from runzi.automation.toshi_api import ModelType
from runzi.tasks.get_config import get_config
from runzi.tasks.inversion.inversion_solution_builder import InversionArgs, InversionSolutionBuilder

if TYPE_CHECKING:
    from py4j.java_gateway import JavaObject

default_submission_args = SubmissionArgs(
    task_language=TaskLanguage.JAVA,
    # java_threads is only used for pbs mode, which is not supported anymore.
    # It should be set to selector_threads * averaging_threads, but this would need to be done task by task if they
    # are swept args. It would be possible to add some inversion specific code to the build_tasks function or find the
    # maximum number of threads before hand or find the maximum number of threads that would be needed before hand.
    java_threads=16,
    # 8 vCPU / 16 GB (2:1) per the #323 crustal benchmark (ADR-0011). Subduction was not benchmarked
    # directly; if a large subduction rupture set OOMs at ~14 GB heap, raise ecs_memory (e.g. 32768).
    # On AWS the heap derives from ecs_memory (memory/1000-2); jvm_heap_max is the LOCAL/CLUSTER -Xmx.
    jvm_heap_max=14,
    ecs_max_job_time_min=60,
    ecs_memory=16384,
    ecs_vcpu=8,
)


class SubductionInversionArgs(InversionArgs):
    """Subduction inversion arguments."""

    scaling_c_val: float | None = None
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
    runtime_args = TaskRuntimeArgs(**config['task_runtime_args'])
    task = SubductionInversionSolutionBuilder(user_args, runtime_args, ModelType.SUBDUCTION)

    # Wait for some more time, scaled by taskid to avoid S3 consistency issue
    time.sleep(runtime_args.task_count)

    task.run()
