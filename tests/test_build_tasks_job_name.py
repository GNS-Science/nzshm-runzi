"""build_tasks must encode the general_task_id into each AWS Batch job name (issue #326), and must
not compound the base name across tasks."""

from unittest.mock import MagicMock, patch


def _run_build_tasks(monkeypatch, general_task_id, n_tasks):
    from runzi import build_tasks as bt
    from runzi.arguments import SubmissionArgs, TaskLanguage
    from runzi.automation.local_config import ClusterModeEnum
    from runzi.automation.toshi_api import ModelType

    monkeypatch.setattr(bt.local_config, 'USE_API', True)
    monkeypatch.setattr(bt.local_config, 'CLUSTER_MODE', ClusterModeEnum.AWS)

    submission_args = SubmissionArgs(
        task_language=TaskLanguage.PYTHON, ecs_max_job_time_min=30, ecs_memory=1024, ecs_vcpu=1
    )

    mock_sweeper = MagicMock()
    mock_sweeper.get_tasks.return_value = [MagicMock() for _ in range(n_tasks)]
    mock_module = MagicMock()
    mock_module.__name__ = 'runzi.tasks.example'

    fake_factory = MagicMock()
    fake_factory.get_container_task.return_value = 'run.sh'
    fake_factory_class = MagicMock()
    fake_factory_class.create.return_value = fake_factory

    job_names = []

    with (
        patch.object(bt, 'get_factory', return_value=fake_factory_class),
        patch.object(bt, 'resolve_job_definition_digest', return_value='sha256:x'),
        patch.object(bt, 'get_ecs_job_config', side_effect=lambda **kw: job_names.append(kw['job_name'])),
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
    return job_names


def test_job_name_carries_general_task_id_prefix(monkeypatch):
    gt_id = 'R2VuZXJhbFRhc2s6MTAxMjI1'
    job_names = _run_build_tasks(monkeypatch, gt_id, n_tasks=2)
    assert job_names == [f'{gt_id}-job-1', f'{gt_id}-job-2']


def test_base_name_does_not_compound_across_tasks(monkeypatch):
    # Regression: the old `job_name = f"{job_name}-{task_count}"` reassigned the shared name, so
    # task 2 became "job-1-2". Each task must derive independently from the base.
    job_names = _run_build_tasks(monkeypatch, 'R2VuZXJhbFRhc2s6MTAxMjI1', n_tasks=3)
    assert all('job-1-' not in name for name in job_names[1:])
