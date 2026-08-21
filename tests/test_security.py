import pytest

from pvc_app import create_app


def test_secret_key_is_required(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError, match="SECRET_KEY must be configured"):
        create_app({"TESTING": True})


def test_csrf_rejects_post_without_token():
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "csrf-test-secret",
            "AUTH_USERNAME": "test-user",
            "AUTH_PASSWORD": "test-password",
            "WTF_CSRF_ENABLED": True,
        }
    )

    response = app.test_client().post(
        "/login",
        data={"username": "test-user", "password": "test-password"},
    )

    assert response.status_code == 400


def test_delete_order_is_post_only(client):
    response = client.get("/delete/1")

    assert response.status_code == 405
