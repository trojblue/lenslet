from __future__ import annotations

from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from lenslet.web.app.base import create_api_app
from lenslet.web.app.builder import _attach_request_context
from lenslet.web.auth import RequestIdentityMiddleware, SESSION_COOKIE_NAME
from lenslet.web.context import RequestContextMiddleware


def test_request_identity_middleware_sets_session_cookie() -> None:
    app = create_api_app(description="test")

    @app.get("/ping")
    def ping():
        return {"ok": True}

    with TestClient(app) as client:
        response = client.get("/ping")

    assert response.status_code == 200
    assert SESSION_COOKIE_NAME in response.cookies


def test_lenslet_request_middlewares_are_pure_asgi() -> None:
    app = create_api_app(description="test")
    _attach_request_context(app)

    middleware_classes = {middleware.cls for middleware in app.user_middleware}

    assert RequestIdentityMiddleware in middleware_classes
    assert RequestContextMiddleware in middleware_classes
    assert BaseHTTPMiddleware not in middleware_classes
