"""Adaptive session cookie Secure flag behavior."""

from evileye.api.middleware.adaptive_session import AdaptiveSessionMiddleware, request_is_https


def test_request_is_https_from_scope_scheme():
    assert request_is_https({"scheme": "https", "headers": []}) is True
    assert request_is_https({"scheme": "http", "headers": []}) is False


def test_request_is_https_from_forwarded_proto():
    scope = {
        "scheme": "http",
        "headers": [(b"x-forwarded-proto", b"https")],
    }
    assert request_is_https(scope) is True


def test_adaptive_session_works_over_http_when_secure_cookies_enabled():
    from fastapi import FastAPI, Request
    from starlette.testclient import TestClient

    app = FastAPI()
    app.add_middleware(
        AdaptiveSessionMiddleware,
        secret_key="x" * 32,
        session_cookie="evileye_session",
        secure_cookies=True,
    )

    @app.post("/login")
    async def login(request: Request):
        request.session["user"] = {"username": "admin", "role": "admin"}
        return {"ok": True}

    @app.get("/me")
    async def me(request: Request):
        return {"user": request.session.get("user")}

    client = TestClient(app)
    login = client.post("/login")
    cookie = login.headers.get("set-cookie") or ""
    assert "secure" not in cookie.lower()
    assert client.get("/me").json()["user"]["username"] == "admin"


def test_adaptive_session_sets_secure_on_https():
    from fastapi import FastAPI, Request
    from starlette.testclient import TestClient

    app = FastAPI()
    app.add_middleware(
        AdaptiveSessionMiddleware,
        secret_key="x" * 32,
        session_cookie="evileye_session",
        secure_cookies=True,
    )

    @app.post("/login")
    async def login(request: Request):
        request.session["user"] = {"username": "admin", "role": "admin"}
        return {"ok": True}

    @app.get("/me")
    async def me(request: Request):
        return {"user": request.session.get("user")}

    client = TestClient(app, base_url="https://testserver")
    login = client.post("/login")
    cookie = login.headers.get("set-cookie") or ""
    assert "; secure" in cookie.lower()
    assert client.get("/me").json()["user"]["username"] == "admin"
