"""Tests for runzi.aws.get_ecs_job_config.

M2M auth config (NZSHM22_TOSHI_M2M_SECRET_ARN, NZSHM22_TOSHI_COGNITO_DOMAIN) is now
the responsibility of the AWS Batch job definition, not runzi. These tests confirm that
runzi never injects those vars into the container environment, so a local submitter's
Scientist credentials are not accidentally overridden by M2M config.
"""

import inspect

import pytest

from runzi.arguments import DEFAULT_JOB_DEFINITION, DEFAULT_JOB_QUEUE, SystemArgs, TaskLanguage
from runzi.aws import get_ecs_job_config
from runzi.aws.aws import BatchEnvironmentSetting, validate_fargate_resources


def _call_get_ecs_job_config(**overrides):
    """Call get_ecs_job_config with sensible defaults; override any param via kwargs."""
    kwargs = dict(
        job_name='test-job-1',
        container_task='run_task.sh',
        model_type=None,
        task_args=None,
        task_system_args=None,
        toshi_api_url='https://api.example.com/graphql',
        toshi_s3_url='https://s3.example.com',
        toshi_report_bucket='my-report-bucket',
        ths_rlz_db=None,
        ths_disagg_rlz_db=None,
        ecr_digest=None,
        task_module='runzi.tasks.oq_hazard.oq_hazard_task',
        time_minutes=60,
        memory=4096,
        vcpu=2,
        job_definition='BasicEC2-job-definition',
        job_queue='BasicEC2-job-queue',
    )
    kwargs.update(overrides)
    return get_ecs_job_config(**kwargs)  # type: ignore[arg-type]


def _env_names(config: dict) -> list[str]:
    """Extract env var names from a get_ecs_job_config result."""
    return [entry['name'] for entry in config['containerOverrides']['environment']]


class TestM2MNotForwarded:
    """M2M auth is now owned by the job definition, not runzi."""

    def test_m2m_secret_arn_not_in_container_env(self, mocker):
        """get_ecs_job_config must never inject NZSHM22_TOSHI_M2M_SECRET_ARN."""
        mocker.patch('runzi.aws.aws.get_task_config', return_value={})

        result = _call_get_ecs_job_config()
        assert 'NZSHM22_TOSHI_M2M_SECRET_ARN' not in _env_names(result)

    def test_cognito_domain_not_in_container_env(self, mocker):
        """get_ecs_job_config must never inject NZSHM22_TOSHI_COGNITO_DOMAIN."""
        mocker.patch('runzi.aws.aws.get_task_config', return_value={})

        result = _call_get_ecs_job_config()
        assert 'NZSHM22_TOSHI_COGNITO_DOMAIN' not in _env_names(result)

    def test_m2m_and_cognito_not_accepted_as_kwargs(self):
        """The function signature must not have m2m_secret_arn or cognito_domain params."""
        sig = inspect.signature(get_ecs_job_config)
        assert 'm2m_secret_arn' not in sig.parameters, (
            'get_ecs_job_config must not accept m2m_secret_arn; M2M config is now supplied by the Batch job definition'
        )
        assert 'cognito_domain' not in sig.parameters, (
            'get_ecs_job_config must not accept cognito_domain; M2M config is now supplied by the Batch job definition'
        )


class TestContainerEnvContents:
    """Sanity-check that the env entries we still own are present."""

    def test_required_env_vars_present(self, mocker):
        """Core env vars that runzi is responsible for must be in the container env."""
        mocker.patch('runzi.aws.aws.get_task_config', return_value={})

        result = _call_get_ecs_job_config()
        names = _env_names(result)

        for required in [
            'TASK_CONFIG_JSON_QUOTED',
            'NZSHM22_TOSHI_API_URL',
            'NZSHM22_TOSHI_S3_URL',
            'NZSHM22_TOSHI_API_ENABLED',
            'AWS_DEFAULT_REGION',
        ]:
            assert required in names, f'{required} missing from container environment'

    def test_extra_env_appended(self, mocker):
        """Extra env entries (from SystemArgs.ecs_extra_env) are appended correctly."""
        mocker.patch('runzi.aws.aws.get_task_config', return_value={})
        extra = [BatchEnvironmentSetting('MY_CUSTOM_VAR', 'hello')]

        result = _call_get_ecs_job_config(extra_env=extra)
        names = _env_names(result)
        assert 'MY_CUSTOM_VAR' in names
        entry = next(e for e in result['containerOverrides']['environment'] if e['name'] == 'MY_CUSTOM_VAR')
        assert entry['value'] == 'hello'

    def test_ths_rlz_db_and_disagg_rlz_db_are_independent(self, mocker):
        """NZSHM22_THS_RLZ_DB and NZSHM22_THS_DISAGG_RLZ_DB must be configurable independently."""
        mocker.patch('runzi.aws.aws.get_task_config', return_value={})
        result = _call_get_ecs_job_config(
            ths_rlz_db='s3://hazard-bucket/rlz',
            ths_disagg_rlz_db='s3://disagg-bucket/rlz',
        )
        env = {e['name']: e['value'] for e in result['containerOverrides']['environment']}
        assert env['NZSHM22_THS_RLZ_DB'] == 's3://hazard-bucket/rlz'
        assert env['NZSHM22_THS_DISAGG_RLZ_DB'] == 's3://disagg-bucket/rlz'

    def test_ths_disagg_rlz_db_defaults_to_working_path_when_none(self, mocker):
        """When ths_disagg_rlz_db is None, NZSHM22_THS_DISAGG_RLZ_DB gets the fallback path."""
        mocker.patch('runzi.aws.aws.get_task_config', return_value={})
        result = _call_get_ecs_job_config(ths_disagg_rlz_db=None)
        env = {e['name']: e['value'] for e in result['containerOverrides']['environment']}
        assert env['NZSHM22_THS_DISAGG_RLZ_DB'] == '/WORKING/THS_DISAGG_RLZ'


class TestValidateFargateResources:
    """validate_fargate_resources enforces the AWS Fargate vCPU/memory matrix."""

    @pytest.mark.parametrize(
        'vcpu, memory',
        [
            (0.25, 512),
            (0.5, 4096),
            (1, 2048),
            (2, 16384),
            (4, 30720),
            (8, 16384),
            (8, 32768),  # the value OQ tasks move to
            (16, 122880),
        ],
    )
    def test_valid_combinations_pass(self, vcpu, memory):
        validate_fargate_resources(vcpu, memory)  # must not raise

    def test_invalid_vcpu_raises(self):
        with pytest.raises(ValueError, match='not a valid Fargate vCPU'):
            validate_fargate_resources(6, 16384)

    def test_invalid_memory_for_vcpu_raises(self):
        # 30000 is not a valid 8-vCPU Fargate memory (must be a multiple of 4096 in 16384..61440).
        with pytest.raises(ValueError, match='not valid for 8 vCPU'):
            validate_fargate_resources(8, 30000)


class TestFargateValidationInJobConfig:
    """get_ecs_job_config validates only when the job definition targets Fargate."""

    def test_invalid_fargate_size_rejected(self, mocker):
        mocker.patch('runzi.aws.aws.get_task_config', return_value={})
        with pytest.raises(ValueError):
            _call_get_ecs_job_config(job_definition=DEFAULT_JOB_DEFINITION, vcpu=8, memory=30000)

    def test_valid_fargate_size_accepted(self, mocker):
        mocker.patch('runzi.aws.aws.get_task_config', return_value={})
        result = _call_get_ecs_job_config(job_definition=DEFAULT_JOB_DEFINITION, vcpu=8, memory=32768)
        assert result['jobDefinition'] == DEFAULT_JOB_DEFINITION

    def test_non_fargate_job_definition_skips_validation(self, mocker):
        """An EC2 job definition skips the Fargate matrix check (interim BigLever path)."""
        mocker.patch('runzi.aws.aws.get_task_config', return_value={})
        result = _call_get_ecs_job_config(vcpu=8, memory=30000)  # BasicEC2 default name
        assert result['jobDefinition'] == 'BasicEC2-job-definition'


class TestSystemArgsComputeDefaults:
    """SystemArgs supplies the single canonical Fargate def/queue by default."""

    def test_job_def_and_queue_default_to_fargate(self):
        args = SystemArgs(
            task_language=TaskLanguage.PYTHON,
            use_api=False,
            ecs_max_job_time_min=10,
            ecs_memory=2048,
            ecs_vcpu=1,
        )
        assert args.ecs_job_definition == DEFAULT_JOB_DEFINITION
        assert args.ecs_job_queue == DEFAULT_JOB_QUEUE
