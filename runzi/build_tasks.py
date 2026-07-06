import os
import stat
from collections.abc import Generator
from pathlib import PurePath
from typing import Any

from runzi.arguments import ArgSweeper, SubmissionArgs, TaskRuntimeArgs
from runzi.automation import local_config
from runzi.automation.local_config import (
    API_URL,
    ECR_DIGEST,
    FATJAR,
    JVM_HEAP_START,
    OPENSHA_JRE,
    OPENSHA_ROOT,
    S3_REPORT_BUCKET,
    S3_URL,
    THS_DISAGG_RLZ_DB,
    THS_RLZ_DB,
    WORK_PATH,
    ClusterModeEnum,
)
from runzi.automation.opensha_task_factory import get_factory
from runzi.automation.toshi_api import ModelType
from runzi.aws import get_ecs_job_config, resolve_job_definition_digest
from runzi.aws.batch_query import batch_job_name
from runzi.protocols import ModuleWithDefaultSubmissionArgs


def build_tasks(
    user_args: ArgSweeper,
    submission_args: SubmissionArgs,
    task_module: ModuleWithDefaultSubmissionArgs,
    model_type: ModelType,
    job_name: str,
    general_task_id: str | None = None,
) -> Generator[dict[str, Any] | str, None, None]:
    """
    build the shell scripts 1 per task, based on all the inputs

    """
    factory_class = get_factory(local_config.CLUSTER_MODE, submission_args.task_language)  # type: ignore

    task_factory = factory_class.create(
        root_path=OPENSHA_ROOT,
        working_path=WORK_PATH,
        python_script_module=task_module,
        jre_path=OPENSHA_JRE,
        app_jar_path=FATJAR,
        task_config_path=WORK_PATH,
        jvm_heap_max=submission_args.jvm_heap_max,
        jvm_heap_start=JVM_HEAP_START,
    )

    # The job definitions track a floating image tag, so resolve the concrete digest the selected
    # job definition currently points at for honest toshi provenance; fall back to the configured
    # NZSHM22_RUNZI_ECR_DIGEST if it can't be resolved (e.g. no AWS access).
    ecr_digest = ECR_DIGEST
    if local_config.CLUSTER_MODE is ClusterModeEnum.AWS:
        ecr_digest = resolve_job_definition_digest(submission_args.ecs_job_definition) or ECR_DIGEST

    for task_count, task_args in enumerate(user_args.get_tasks(), start=1):
        # Assemble the per-task runtime context the worker needs. This is the only args model shipped
        # to the worker; submission-only config (queue, compute env, sizing) stays submitter-side.
        task_runtime_args = TaskRuntimeArgs(
            general_task_id=general_task_id,
            use_api=local_config.USE_API,
            task_count=task_count,
            java_threads=submission_args.java_threads,
        )

        if local_config.CLUSTER_MODE is ClusterModeEnum.AWS:
            container_task = task_factory.get_container_task()

            # Encode the general_task_id into the job name so `runzi batch` can find this task's jobs
            # via a list_jobs JOB_NAME prefix filter (issue #326). Derive from the base `job_name` each
            # iteration — never reassign it, or the base would compound across tasks (job-1, job-1-2, …).
            task_job_name = batch_job_name(general_task_id, job_name, task_count)

            yield get_ecs_job_config(
                container_task=container_task,
                model_type=model_type,
                job_name=task_job_name,
                task_args=task_args,
                task_runtime_args=task_runtime_args,
                toshi_api_url=API_URL,
                toshi_s3_url=S3_URL,
                toshi_report_bucket=S3_REPORT_BUCKET,
                ths_rlz_db=THS_RLZ_DB,
                ths_disagg_rlz_db=THS_DISAGG_RLZ_DB,
                ecr_digest=ecr_digest,
                task_module=task_module.__name__,
                time_minutes=submission_args.ecs_max_job_time_min,
                memory=submission_args.ecs_memory,
                vcpu=submission_args.ecs_vcpu,
                job_definition=submission_args.ecs_job_definition,
                job_queue=submission_args.resolved_job_queue,
                extra_env=submission_args.ecs_extra_env,
                use_compression=True,
                compute_environment=submission_args.resolved_compute_environment,
            )

        else:
            # write a config
            task_factory.write_task_config(task_args, task_runtime_args, model_type)

            script = task_factory.get_task_script()

            script_file_path = PurePath(WORK_PATH, f"task_{task_count}.sh")
            with open(script_file_path, "w") as f:
                f.write(script)

            # make file executable
            st = os.stat(script_file_path)
            os.chmod(script_file_path, st.st_mode | stat.S_IEXEC)

            yield str(script_file_path)
