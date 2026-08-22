import pytest
from fastapi import HTTPException, Request

from src.dependencies import get_current_user
from src.models.user import User


def _dev_request() -> Request:
    return Request({"type": "http", "headers": []})


def _prod_request(claims: dict) -> Request:
    scope = {
        "type": "http",
        "headers": [],
        "aws.event": {"requestContext": {"authorizer": {"jwt": {"claims": claims}}}},
    }
    return Request(scope)


def test_get_current_user_creates_user_in_dev_mode(db_session, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("LOCAL_DEV_COGNITO_SUB", "local-dev-user")

    user = get_current_user(_dev_request(), db_session)

    assert isinstance(user, User)
    assert user.cognito_sub == "local-dev-user"
    assert db_session.query(User).filter(User.cognito_sub == "local-dev-user").count() == 1


def test_get_current_user_is_idempotent_for_same_sub(db_session, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("LOCAL_DEV_COGNITO_SUB", "local-dev-user")

    first = get_current_user(_dev_request(), db_session)
    second = get_current_user(_dev_request(), db_session)

    assert first.id == second.id
    assert db_session.query(User).filter(User.cognito_sub == "local-dev-user").count() == 1


def test_get_current_user_reads_cognito_sub_from_jwt_claims(db_session, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prod")

    user = get_current_user(_prod_request({"sub": "cognito-sub-123"}), db_session)

    assert user.cognito_sub == "cognito-sub-123"


def test_get_current_user_rejects_missing_sub_claim(db_session, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prod")

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(_prod_request({}), db_session)

    assert exc_info.value.status_code == 401
