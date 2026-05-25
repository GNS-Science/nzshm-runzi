"""Tests for runzi.aws.session.get_session()."""

import logging

import boto3
import pytest

from runzi.aws import session as session_mod


@pytest.fixture
def fake_auth_config():
    return {
        'cognito_domain': 'auth.example.com',
        'scientist_client_id': 'abc123',
        'region': 'ap-southeast-2',
        'user_pool_id': 'ap-southeast-2_FAKE',
        'identity_pool_id': 'ap-southeast-2:fake-pool',
    }


@pytest.fixture
def fake_sts_creds():
    return {
        'AccessKeyId': 'AKIAFAKE',
        'SecretKey': 'fakesecret',
        'SessionToken': 'faketoken',
    }


def test_cognito_path_returns_session_with_sts_creds(mocker, fake_auth_config, fake_sts_creds):
    mocker.patch(
        'nshm_toshi_client.auth.load_credentials',
        return_value={'access_token': 'eyJ-fresh-token'},
    )
    mocker.patch('nshm_toshi_client.cli.load_auth_config', return_value=fake_auth_config)
    mocker.patch(
        'nshm_toshi_client.auth.ToshiCredentialAuth._get_token',
        return_value='eyJ-fresh-token',
    )
    ci_client = mocker.Mock()
    ci_client.get_id.return_value = {'IdentityId': 'identity-xyz'}
    ci_client.get_credentials_for_identity.return_value = {'Credentials': fake_sts_creds}
    boto3_client = mocker.patch.object(session_mod.boto3, 'client', return_value=ci_client)

    sess = session_mod.get_session()

    boto3_client.assert_called_once_with('cognito-identity', region_name='ap-southeast-2')
    expected_provider = 'cognito-idp.ap-southeast-2.amazonaws.com/ap-southeast-2_FAKE'
    ci_client.get_id.assert_called_once_with(
        IdentityPoolId='ap-southeast-2:fake-pool',
        Logins={expected_provider: 'eyJ-fresh-token'},
    )
    ci_client.get_credentials_for_identity.assert_called_once_with(
        IdentityId='identity-xyz',
        Logins={expected_provider: 'eyJ-fresh-token'},
    )
    assert isinstance(sess, boto3.Session)
    frozen = sess.get_credentials().get_frozen_credentials()
    assert frozen.access_key == 'AKIAFAKE'
    assert frozen.secret_key == 'fakesecret'
    assert frozen.token == 'faketoken'


def test_no_cognito_credentials_falls_back_to_default(mocker):
    mocker.patch('nshm_toshi_client.auth.load_credentials', return_value={})
    load_config = mocker.patch('nshm_toshi_client.cli.load_auth_config')
    boto3_client = mocker.patch.object(session_mod.boto3, 'client')
    default_sess = mocker.Mock(spec=boto3.Session)
    session_ctor = mocker.patch.object(session_mod.boto3, 'Session', return_value=default_sess)

    sess = session_mod.get_session()

    load_config.assert_not_called()
    boto3_client.assert_not_called()
    session_ctor.assert_called_once_with()
    assert sess is default_sess


def test_incomplete_auth_config_falls_back_to_default(mocker):
    mocker.patch(
        'nshm_toshi_client.auth.load_credentials',
        return_value={'access_token': 'eyJ-fresh-token'},
    )
    # identity_pool_id missing -> bail out
    mocker.patch(
        'nshm_toshi_client.cli.load_auth_config',
        return_value={
            'cognito_domain': 'auth.example.com',
            'scientist_client_id': 'abc123',
            'region': 'ap-southeast-2',
            'user_pool_id': 'ap-southeast-2_FAKE',
        },
    )
    boto3_client = mocker.patch.object(session_mod.boto3, 'client')
    default_sess = mocker.Mock(spec=boto3.Session)
    session_ctor = mocker.patch.object(session_mod.boto3, 'Session', return_value=default_sess)

    sess = session_mod.get_session()

    boto3_client.assert_not_called()
    session_ctor.assert_called_once_with()
    assert sess is default_sess


def test_token_refresh_failure_logs_warning_and_falls_back(mocker, caplog, fake_auth_config):
    mocker.patch(
        'nshm_toshi_client.auth.load_credentials',
        return_value={'access_token': 'eyJ-stale-token'},
    )
    mocker.patch('nshm_toshi_client.cli.load_auth_config', return_value=fake_auth_config)
    mocker.patch(
        'nshm_toshi_client.auth.ToshiCredentialAuth._get_token',
        side_effect=RuntimeError('Token expired and no refresh token. Run: toshi-auth login'),
    )
    boto3_client = mocker.patch.object(session_mod.boto3, 'client')
    default_sess = mocker.Mock(spec=boto3.Session)
    session_ctor = mocker.patch.object(session_mod.boto3, 'Session', return_value=default_sess)

    with caplog.at_level(logging.WARNING, logger=session_mod.log.name):
        sess = session_mod.get_session()

    boto3_client.assert_not_called()
    session_ctor.assert_called_once_with()
    assert sess is default_sess
    assert any('Cognito AWS auth unavailable' in rec.message for rec in caplog.records)


def test_cognito_identity_failure_falls_back(mocker, caplog, fake_auth_config):
    mocker.patch(
        'nshm_toshi_client.auth.load_credentials',
        return_value={'access_token': 'eyJ-fresh-token'},
    )
    mocker.patch('nshm_toshi_client.cli.load_auth_config', return_value=fake_auth_config)
    mocker.patch(
        'nshm_toshi_client.auth.ToshiCredentialAuth._get_token',
        return_value='eyJ-fresh-token',
    )
    ci_client = mocker.Mock()
    ci_client.get_id.side_effect = Exception('NotAuthorizedException')
    mocker.patch.object(session_mod.boto3, 'client', return_value=ci_client)
    default_sess = mocker.Mock(spec=boto3.Session)
    session_ctor = mocker.patch.object(session_mod.boto3, 'Session', return_value=default_sess)

    with caplog.at_level(logging.WARNING, logger=session_mod.log.name):
        sess = session_mod.get_session()

    session_ctor.assert_called_once_with()
    assert sess is default_sess
    assert any('Cognito AWS auth unavailable' in rec.message for rec in caplog.records)
