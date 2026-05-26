"""AWS session factory: prefers Cognito-derived STS credentials, falls back
to the default boto3 credential chain (AWS_PROFILE, ~/.aws/credentials, env
vars, IAM role).
"""

import logging

import boto3

log = logging.getLogger(__name__)


def get_session() -> boto3.Session:
    """Return a boto3.Session backed by Cognito Identity Pool credentials when
    ``toshi-auth login`` has produced a usable token, otherwise the default
    boto3 credential chain.
    """
    try:
        from nshm_toshi_client.aws import CognitoAuthError, get_aws_session
    except ImportError as exc:
        log.warning(
            "Cognito AWS auth unavailable: nshm_toshi_client not importable (%s); "
            "falling back to default credential chain.",
            exc,
        )
        return boto3.Session()

    try:
        return get_aws_session()
    except CognitoAuthError as exc:
        log.warning(
            "Cognito AWS auth unavailable: %s; falling back to default credential chain. "
            "Run `toshi-auth login` if you intended to use Cognito.",
            exc,
        )
        return boto3.Session()
