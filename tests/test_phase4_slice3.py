import httpx
import pytest

from server.app import create_app
from server.config import Settings, load_settings
from server.scenario import DEFAULT_CONTEXT
from tests.test_phase3_slice1 import TEST_SETTINGS


def test_config_parses_phase4_demo_security_and_rate_limit_settings():
    settings = load_settings({
        "ALLOWED_HOSTS": "Demo.Example.com, staging.local , ",
        "DEMO_ACCESS_TOKEN": "shared-secret-token",
        "RATE_LIMIT_PER_MINUTE": "25",
    })
    assert settings.allowed_hosts == ("demo.example.com", "staging.local")
    assert settings.demo_access_token == "shared-secret-token"
    assert settings.rate_limit_per_minute == 25
    assert "shared-secret-token" not in repr(settings)

    for bad in ("-1", "abc"):
        with pytest.raises(ValueError, match="RATE_LIMIT_PER_MINUTE"):
            load_settings({"RATE_LIMIT_PER_MINUTE": bad})


@pytest.mark.anyio
async def test_allowed_hosts_and_https_origin_with_hsts_header():
    settings = Settings(**{**TEST_SETTINGS.__dict__, "allowed_hosts": ("demo.example.com",)})
    app = create_app(settings_loader=lambda: settings)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://demo.example.com") as client:
        res = await client.get(
            "/api/config",
            headers={
                "Host": "demo.example.com",
                "Origin": "https://demo.example.com",
                "X-Forwarded-Proto": "https",
            },
        )
        assert res.status_code == 200
        assert "strict-transport-security" in res.headers

        bad = await client.get("/api/config", headers={"Host": "evil.example.com"})
        assert bad.status_code == 403
        assert bad.json()["error"]["code"] == "INVALID_ORIGIN"


@pytest.mark.anyio
async def test_demo_access_token_protects_api_without_leaking_token():
    secret = "demo-token-xyz-987"
    settings = Settings(**{**TEST_SETTINGS.__dict__, "demo_access_token": secret})
    app = create_app(settings_loader=lambda: settings)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:4317") as client:
        cfg = await client.get("/api/config")
        assert cfg.status_code == 200
        assert cfg.json()["accessRequired"] is True
        assert secret not in cfg.text

        no_token = await client.post(
            "/api/practice",
            json={"context": DEFAULT_CONTEXT, "requestId": "phase4-slice3-auth-001"},
        )
        assert no_token.status_code == 401
        assert no_token.json()["error"]["code"] == "ACCESS_REQUIRED"

        wrong_token = await client.post(
            "/api/practice",
            json={"context": DEFAULT_CONTEXT, "requestId": "phase4-slice3-auth-002"},
            headers={"X-DevBridge-Token": "wrong"},
        )
        assert wrong_token.status_code == 401

        ok_header = await client.post(
            "/api/practice",
            json={"context": DEFAULT_CONTEXT, "requestId": "phase4-slice3-auth-003"},
            headers={"X-DevBridge-Token": secret},
        )
        assert ok_header.status_code == 200

        ok_bearer = await client.post(
            "/api/practice",
            json={"context": DEFAULT_CONTEXT, "requestId": "phase4-slice3-auth-004"},
            headers={"Authorization": f"Bearer {secret}"},
        )
        assert ok_bearer.status_code == 200


@pytest.mark.anyio
async def test_sliding_window_rate_limit_enforces_429_and_recovers_after_window():
    now = 100.0
    settings = Settings(**{**TEST_SETTINGS.__dict__, "rate_limit_per_minute": 2})
    app = create_app(settings_loader=lambda: settings, clock=lambda: now)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:4317") as client:
        cfg = await client.get("/api/config")
        assert cfg.status_code == 200
        assert cfg.json()["rateLimitPerMinute"] == 2

        r1 = await client.post("/api/practice", json={"context": DEFAULT_CONTEXT, "requestId": "phase4-slice3-rate-001"})
        r2 = await client.post("/api/practice", json={"context": DEFAULT_CONTEXT, "requestId": "phase4-slice3-rate-002"})
        r3 = await client.post("/api/practice", json={"context": DEFAULT_CONTEXT, "requestId": "phase4-slice3-rate-003"})
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r3.status_code == 429
        assert r3.json()["error"]["code"] == "RATE_LIMITED"

        now += 61.0
        r4 = await client.post("/api/practice", json={"context": DEFAULT_CONTEXT, "requestId": "phase4-slice3-rate-004"})
        assert r4.status_code == 200


@pytest.mark.anyio
async def test_cross_site_top_level_navigation_allowed_while_cross_site_api_blocked():
    settings = Settings(**{**TEST_SETTINGS.__dict__, "allowed_hosts": ("demo.example.com",)})
    app = create_app(settings_loader=lambda: settings)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://demo.example.com") as client:
        nav = await client.get(
            "/",
            headers={
                "Host": "demo.example.com",
                "Sec-Fetch-Site": "cross-site",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Dest": "document",
            },
        )
        assert nav.status_code == 200

        api_nav = await client.get(
            "/api/config",
            headers={
                "Host": "demo.example.com",
                "Sec-Fetch-Site": "cross-site",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Dest": "document",
            },
        )
        assert api_nav.status_code == 403

        subresource = await client.get(
            "/",
            headers={
                "Host": "demo.example.com",
                "Sec-Fetch-Site": "cross-site",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Dest": "empty",
            },
        )
        assert subresource.status_code == 200

        api_post = await client.post(
            "/api/practice",
            json={"context": DEFAULT_CONTEXT, "requestId": "phase4-slice3-csrf-001"},
            headers={
                "Host": "demo.example.com",
                "Sec-Fetch-Site": "cross-site",
            },
        )
        assert api_post.status_code == 403

