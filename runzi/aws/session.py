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
    cognito = _try_cognito_session()
    return cognito if cognito is not None else boto3.Session()


def _try_cognito_session() -> boto3.Session | None:
    try:
        from nshm_toshi_client.auth import ToshiCredentialAuth, load_credentials
        from nshm_toshi_client.cli import load_auth_config
    except ImportError:
        return None

    try:
        creds = load_credentials()
        if not creds.get('access_token'):
            return None

        # load_auth_config may raise click.ClickException if scientist_client_id
        # is missing; caught by the outer Exception handler below.
        config = load_auth_config()
        try:
            identity_pool_id: str = config['identity_pool_id']
            user_pool_id: str = config['user_pool_id']
            region: str = config['region']
            domain: str = config['cognito_domain']
            scientist_client_id: str = config['scientist_client_id']
        except KeyError:
            return None
        if not all([identity_pool_id, user_pool_id, region, domain, scientist_client_id]):
            return None

        # _get_token() refreshes transparently if the access token is expired,
        # and raises RuntimeError if no refresh token / refresh fails.
        access_token = ToshiCredentialAuth(domain, scientist_client_id)._get_token()

        login_provider = f'cognito-idp.{region}.amazonaws.com/{user_pool_id}'
        ci = boto3.client('cognito-identity', region_name=region)
        identity_id = ci.get_id(
            IdentityPoolId=identity_pool_id,
            Logins={login_provider: access_token},
        )['IdentityId']
        sts = ci.get_credentials_for_identity(
            IdentityId=identity_id,
            Logins={login_provider: access_token},
        )['Credentials']

        log.info("Using Cognito-federated AWS credentials (identity %s)", identity_id)
        return boto3.Session(
            aws_access_key_id=sts['AccessKeyId'],
            aws_secret_access_key=sts['SecretKey'],
            aws_session_token=sts['SessionToken'],
        )
    except Exception as exc:
        log.warning(
            "Cognito AWS auth unavailable (%s); falling back to default boto3 "
            "credential chain. Run `toshi-auth login` if you intended to use "
            "Cognito.",
            exc,
        )
        return None
