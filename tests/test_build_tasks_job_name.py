"""build_tasks must encode the general_task_id into each AWS Batch job name (issue #326), and must
not compound the base name across tasks. It also assembles the per-task TaskRuntimeArgs shipped to the
worker — including deriving OpenQuake's core cap (allocated_vcpu) from ecs_vcpu (ADR-0012)."""

from unittest.mock import MagicMock, patch


def _run_build_tasks(monkeypatch, general_task_id, n_tasks, *, java_threads=None, ecs_vcpu=1):
    """Run build_tasks in AWS mode with the factory/ECS calls mocked; return each get_ecs_job_config
    call's kwargs (which include ``job_name`` and the shipped ``task_runtime_args``)."""
    from runzi import build_tasks as bt
    from runzi.arguments import SubmissionArgs, TaskLanguage
    from runzi.automation.local_config import ClusterModeEnum
    from runzi.automation.toshi_api import ModelType

    monkeypatch.setattr(bt.local_config, 'USE_API', True)
    monkeypatch.setattr(bt.local_config, 'CLUSTER_MODE', ClusterModeEnum.AWS)

    submission_args = SubmissionArgs(
        task_language=TaskLanguage.PYTHON,
        ecs_max_job_time_min=30,
        ecs_memory=1024,
        ecs_vcpu=ecs_vcpu,
        java_threads=java_threads,
    )

    mock_sweeper = MagicMock()
    mock_sweeper.get_tasks.return_value = [MagicMock() for _ in range(n_tasks)]
    mock_module = MagicMock()
    mock_module.__name__ = 'runzi.tasks.example'

    fake_factory = MagicMock()
    fake_factory.get_container_task.return_value = 'run.sh'
    fake_factory_class = MagicMock()
    fake_factory_class.create.return_value = fake_factory

    calls = []

    with (
        patch.object(bt, 'get_factory', return_value=fake_factory_class),
        patch.object(bt, 'resolve_job_definition_digest', return_value='sha256:x'),
        patch.object(bt, 'get_ecs_job_config', side_effect=lambda **kw: calls.append(kw)),
    ):
        list(
            bt.build_tasks(
                mock_sweeper,
                submission_args,
                mock_module,
                ModelType.CRUSTAL,
                'job',
                general_task_id=general_task_id,
            )
        )
    return calls


def test_job_name_carries_general_task_id_prefix(monkeypatch):
    gt_id = 'R2VuZXJhbFRhc2s6MTAxMjI1'
    calls = _run_build_tasks(monkeypatch, gt_id, n_tasks=2)
    assert [c['job_name'] for c in calls] == [f'{gt_id}-job-1', f'{gt_id}-job-2']


def test_base_name_does_not_compound_across_tasks(monkeypatch):
    # Regression: the old `job_name = f"{job_name}-{task_count}"` reassigned the shared name, so
    # task 2 became "job-1-2". Each task must derive independently from the base.
    calls = _run_build_tasks(monkeypatch, 'R2VuZXJhbFRhc2s6MTAxMjI1', n_tasks=3)
    assert all('job-1-' not in c['job_name'] for c in calls[1:])


def test_ships_allocated_vcpu_from_ecs_vcpu_and_java_threads_from_its_own_field(monkeypatch):
    # ADR-0012: the worker's OpenQuake core cap is derived from ecs_vcpu (shipped as allocated_vcpu),
    # NOT from a hand-set field that could drift; java_threads carries the separate Java thread knob.
    # Distinct values prove the two runtime fields come from different SubmissionArgs sources.
    calls = _run_build_tasks(monkeypatch, 'R2VuZXJhbFRhc2s6MTAxMjI1', n_tasks=1, java_threads=4, ecs_vcpu=8)
    runtime_args = calls[0]['task_runtime_args']
    assert runtime_args.allocated_vcpu == 8  # = ecs_vcpu; OpenQuake caps its processpool to this on Batch EC2
    assert runtime_args.java_threads == 4  # the Java knob, not aliased to vCPU
