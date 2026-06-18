"""Tests for runzi.cli.build_and_deploy_container.update_job_definition.

register_job_definition defaults platformCapabilities to EC2 when it is omitted, and EC2
rejects fractional vCPU values (e.g. 0.25) used by Fargate job definitions. update_job_definition
must forward the existing job definition's platformCapabilities so re-registration keeps
validating against Fargate.
"""

from runzi.cli.build_and_deploy_container import update_job_definition


def _describe_job_definitions_response(platform_capabilities):
    return {
        "jobDefinitions": [
            {
                "revision": 3,
                "jobDefinitionArn": "arn:aws:batch:us-east-1:123456789012:job-definition/Fargate-runzi-opensha-JD:3",
                "parameters": {},
                "containerProperties": {
                    "image": "old-image",
                    "resourceRequirements": [{"value": "0.25", "type": "VCPU"}],
                },
                "platformCapabilities": platform_capabilities,
            }
        ]
    }


def test_forwards_platform_capabilities_on_reregister(mocker):
    """register_job_definition must be called with the source definition's platformCapabilities."""
    mock_client = mocker.Mock()
    mock_client.describe_job_definitions.return_value = _describe_job_definitions_response(["FARGATE"])
    mock_client.register_job_definition.return_value = {
        "jobDefinitionArn": "arn:aws:batch:us-east-1:123456789012:job-definition/Fargate-runzi-opensha-JD:4",
        "revision": 4,
    }
    mocker.patch("boto3.client", return_value=mock_client)

    update_job_definition("Fargate-runzi-opensha-JD", "new-image", "us-east-1")

    _, kwargs = mock_client.register_job_definition.call_args
    assert kwargs["platformCapabilities"] == ["FARGATE"]
