"""Tests for runzi.aws.session.get_session().

The Cognito federation logic lives in nshm_toshi_client.aws.get_aws_session(),
which is library-internal and tested upstream. Runzi only owns the fallback
wrapper: prefer Cognito; on any CognitoAuthError or ImportError, log a warning
and return the default boto3 credential chain.
"""

import logging
import sys

import boto3

from runzi.aws import session as session_mod


def test_cognito_path_returns_session_from_library(mocker, monkeypatch):
    """When nshm_toshi_client.aws.get_aws_session succeeds, get_session passes
    its return value straight through."""
    monkeypatch.delenv('AWS_PROFILE', raising=False)
    fake_session = mocker.Mock(spec=boto3.Session)
    mocker.patch('nshm_toshi_client.aws.get_aws_session', return_value=fake_session)

    assert session_mod.get_session() is fake_session


def test_cognito_auth_error_falls_back(mocker, caplog):
    """A CognitoAuthError (or any subclass) from the library is caught;
    get_session logs a WARNING and returns the default boto3.Session()."""
    from nshm_toshi_client.aws import NoCredentialsError

    mocker.patch(
        'nshm_toshi_client.aws.get_aws_session',
        side_effect=NoCredentialsError("No credentials found. Run: toshi-auth login"),
    )
    default_sess = mocker.Mock(spec=boto3.Session)
    session_ctor = mocker.patch.object(session_mod.boto3, 'Session', return_value=default_sess)

    with caplog.at_level(logging.WARNING, logger=session_mod.log.name):
        sess = session_mod.get_session()

    session_ctor.assert_called_once_with()
    assert sess is default_sess
    assert any('Cognito AWS auth unavailable' in rec.message for rec in caplog.records)
    assert any('No credentials found' in rec.message for rec in caplog.records)


def test_import_error_falls_back(mocker, caplog):
    """If nshm_toshi_client.aws is not importable, log a WARNING and return
    the default boto3.Session()."""
    mocker.patch.dict(sys.modules, {'nshm_toshi_client.aws': None})
    default_sess = mocker.Mock(spec=boto3.Session)
    session_ctor = mocker.patch.object(session_mod.boto3, 'Session', return_value=default_sess)

    with caplog.at_level(logging.WARNING, logger=session_mod.log.name):
        sess = session_mod.get_session()

    session_ctor.assert_called_once_with()
    assert sess is default_sess
    assert any('nshm_toshi_client not importable' in rec.message for rec in caplog.records)
