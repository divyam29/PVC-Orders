def test_feature_routes_require_login(app):
    client = app.test_client()

    response = client.get("/orders")

    assert response.status_code == 302
    assert response.headers["Location"] == "/login?next=/orders"


def test_login_and_logout(app):
    client = app.test_client()

    login_response = client.post(
        "/login",
        data={"username": "test-user", "password": "test-password"},
    )
    assert login_response.status_code == 302
    assert login_response.headers["Location"] == "/"

    logout_response = client.post("/logout")
    assert logout_response.status_code == 302
    assert logout_response.headers["Location"] == "/login"
    assert client.get("/orders").status_code == 302