"""AWS session factory: prefers Cognito-derived STS credentials, falls back
to the default boto3 credential chain (AWS_PROFILE, ~/.aws/credentials, env
vars, IAM role).
"""

import logging
from pathlib import Path

import boto3

log = logging.getLogger(__name__)

_REQUIRED_CONFIG_KEYS = (
    'identity_pool_id',
    'user_pool_id',
    'region',
    'cognito_domain',
    'scientist_client_id',
)

_FALLBACK_SUFFIX = "falling back to default credential chain."


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
    except ImportError as exc:
        log.warning("Cognito AWS auth unavailable: nshm_toshi_client not importable (%s); %s", exc, _FALLBACK_SUFFIX)
        return None

    toshi_dir = Path.home() / '.toshi'
    log.debug(
        "Cognito AWS auth attempt: HOME=%s, credentials_exists=%s, auth_config_exists=%s",
        Path.home(),
        (toshi_dir / 'credentials').exists(),
        (toshi_dir / 'auth_config.json').exists(),
    )

    try:
        creds = load_credentials()
        if not creds.get('access_token'):
            log.warning(
                "Cognito AWS auth unavailable: ~/.toshi/credentials has no access_token (run `toshi-auth login`); %s",
                _FALLBACK_SUFFIX,
            )
            return None

        # load_auth_config may raise click.ClickException if scientist_client_id
        # is missing; caught by the outer Exception handler below.
        config = load_auth_config()
        missing = [k for k in _REQUIRED_CONFIG_KEYS if not config.get(k)]
        if missing:
            log.warning(
                "Cognito AWS auth unavailable: auth config missing key(s) %s "
                "(expected in ~/.toshi/auth_config.json); %s",
                missing,
                _FALLBACK_SUFFIX,
            )
            return None

        identity_pool_id: str = config['identity_pool_id']
        user_pool_id: str = config['user_pool_id']
        region: str = config['region']
        domain: str = config['cognito_domain']
        scientist_client_id: str = config['scientist_client_id']

        # Trigger a refresh if the access_token is expired; this also refreshes
        # id_token in ~/.toshi/credentials. Raises RuntimeError if no refresh
        # token / refresh fails.
        ToshiCredentialAuth(domain, scientist_client_id)._get_token()

        # Cognito Identity Pool requires an id_token (not access_token) in the
        # Logins map — id_token carries the `aud` claim that the pool validates.
        id_token = load_credentials().get('id_token')
        if not id_token:
            log.warning(
                "Cognito AWS auth unavailable: ~/.toshi/credentials has no id_token (re-run `toshi-auth login`); %s",
                _FALLBACK_SUFFIX,
            )
            return None

        login_provider = f'cognito-idp.{region}.amazonaws.com/{user_pool_id}'
        ci = boto3.client('cognito-identity', region_name=region)
        identity_id = ci.get_id(
            IdentityPoolId=identity_pool_id,
            Logins={login_provider: id_token},
        )['IdentityId']
        sts = ci.get_credentials_for_identity(
            IdentityId=identity_id,
            Logins={login_provider: id_token},
        )['Credentials']

        log.info("Using Cognito-federated AWS credentials (identity %s)", identity_id)
        return boto3.Session(
            aws_access_key_id=sts['AccessKeyId'],
            aws_secret_access_key=sts['SecretKey'],
            aws_session_token=sts['SessionToken'],
        )
    except Exception as exc:
        log.warning(
            "Cognito AWS auth unavailable (%s); %s Run `toshi-auth login` if you intended to use Cognito.",
            exc,
            _FALLBACK_SUFFIX,
        )
        return None
