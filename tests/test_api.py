import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from warmane_api.client import UpstreamError, WarmaneClient
from warmane_api.main import app
from warmane_api.normalize import normalize


CHARACTER = {"name": "Dojun", "realm": "Icecrown", "level": "80", "online": "0",
             "achievementpoints": None, "equipment": [{"item": "46191", "transmog": ""}],
             "talents": [{"tree": "Balance", "points": [None, "0", "13"]}]}


def test_normalization_preserves_unknowns():
    result = normalize({**CHARACTER, "unknown": "123", "guild": "007"})
    assert result["level"] == 80
    assert result["online"] is False
    assert result["achievementpoints"] == 0
    assert result["talents"][0]["points"] == [0, 0, 13]
    assert result["equipment"][0] == {"item": 46191, "transmog": ""}
    assert result["unknown"] == "123" and result["guild"] == "007"
    assert normalize({"online": None})["online"] is None
    assert CHARACTER["level"] == "80"


@pytest.fixture
def api():
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json=CHARACTER)
    with TestClient(app) as client:
        app.state.warmane = WarmaneClient(httpx.AsyncClient(
            base_url="https://armory.warmane.com/api/", transport=httpx.MockTransport(handler)), interval=0)
        yield client, calls
        client.portal.call(app.state.warmane.http.aclose)


def test_summary_sections_raw_and_cache(api):
    client, calls = api
    url = "/api/v1/characters/Icecrown/Dojun"
    first = client.get(url + "/summary").json()
    assert first["data"]["level"] == 80 and first["meta"]["cached"] is False
    raw = client.get(url + "/summary?raw=true").json()
    assert raw["data"]["level"] == "80" and raw["meta"]["cached"] is True
    assert client.get(url + "/equipment").json()["data"][0]["item"] == 46191
    assert client.get(url + "/status").json()["data"]["online"] is False
    assert client.get(url + "/professions").json()["data"] is None
    assert len(calls) == 1


def test_validation_and_docs(api):
    client, calls = api
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/docs").status_code == 200
    assert client.get("/", follow_redirects=False).headers["location"] == "/docs"
    assert not any("/guilds/" in path for path in client.get("/openapi.json").json()["paths"])
    assert client.get("/api/v1/characters/Icecrown/%20").status_code == 422
    assert client.get("/api/v1/characters/Icecrown/Foo%3Fbar").status_code == 422
    assert client.get("/api/v1/characters/Icecrown/Dojun/invalid").status_code == 422
    assert calls == []


def test_unknown_status_is_not_reported_as_offline(api, monkeypatch):
    client, _ = api
    async def unknown(*args, **kwargs):
        return {"name": "Dojun", "realm": "Icecrown", "online": "unknown"}, {
            "cached": False, "fetched_at": "2026-09-23T00:00:00+00:00", "cache_ttl_seconds": 60}
    monkeypatch.setattr(app.state.warmane, "summary", unknown)
    response = client.get("/api/v1/characters/Icecrown/Dojun/status")
    assert response.status_code == 200
    assert response.json()["data"]["online"] is None


@pytest.mark.parametrize("response,status,code", [
    (httpx.Response(200, json={"error": "123"}), 502, "upstream_api_error"),
    (httpx.Response(200, text="<html>Challenge</html>"), 502, "invalid_upstream_response"),
    (httpx.Response(200, json=[]), 502, "invalid_upstream_response"),
    (httpx.Response(200, json={}), 502, "invalid_upstream_response"),
    (httpx.Response(404), 404, "not_found"),
    (httpx.Response(500), 502, "upstream_http_error"),
    (httpx.Response(429, headers={"Retry-After": "90"}), 503, "upstream_rate_limited"),
])
def test_upstream_errors(response, status, code):
    with TestClient(app) as client:
        app.state.warmane = WarmaneClient(httpx.AsyncClient(base_url="https://example.test/",
            transport=httpx.MockTransport(lambda _: response)), interval=0)
        result = client.get("/api/v1/characters/Icecrown/Dojun")
        assert result.status_code == status
        assert result.json()["error"]["code"] == code
        assert not app.state.warmane.cache
        if code == "upstream_api_error":
            assert result.json()["error"]["upstream_error"] == "123"
            assert result.headers["retry-after"] == "60"
        if status == 503:
            assert result.headers["retry-after"] == "90"
        client.portal.call(app.state.warmane.http.aclose)


@pytest.mark.parametrize("exception,status", [(httpx.ReadTimeout("timeout"), 504), (httpx.ConnectError("offline"), 502)])
def test_network_errors(exception, status):
    async def run():
        def handler(_):
            raise exception
        async with httpx.AsyncClient(base_url="https://example.test/", transport=httpx.MockTransport(handler)) as http:
            with pytest.raises(UpstreamError) as caught:
                await WarmaneClient(http).summary("character", "Dojun", "Icecrown")
            assert caught.value.status == status
    asyncio.run(run())


def test_cooldown_expiry_eviction_and_cache_isolation():
    async def run():
        async with httpx.AsyncClient(base_url="https://example.test/", transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json=CHARACTER))) as http:
            client = WarmaneClient(http, interval=4, capacity=1)
            data, _ = await client.summary("character", "A", "Icecrown")
            data["name"] = "mutated"
            cached, meta = await client.summary("character", "A", "Icecrown")
            assert cached["name"] == "Dojun" and meta["cached"]
            with pytest.raises(UpstreamError) as caught:
                await client.summary("character", "B", "Icecrown")
            assert caught.value.status == 503
            client.next_request = 0
            await client.summary("character", "B", "Icecrown")
            assert len(client.cache) == 1 and next(iter(client.cache)).startswith("character/B/")
            client.next_request = 0
            key = next(iter(client.cache))
            entry = client.cache[key]
            client.cache[key] = (0, entry[1], entry[2])
            _, meta = await client.summary("character", "B", "Icecrown")
            assert not meta["cached"]
    asyncio.run(run())


def test_concurrent_misses_fail_fast():
    async def run():
        entered, release = asyncio.Event(), asyncio.Event()
        async def handler(_):
            entered.set()
            await release.wait()
            return httpx.Response(200, json=CHARACTER)
        async with httpx.AsyncClient(base_url="https://example.test/", transport=httpx.MockTransport(handler)) as http:
            client = WarmaneClient(http, interval=0)
            first = asyncio.create_task(client.summary("character", "A", "Icecrown"))
            await entered.wait()
            try:
                with pytest.raises(UpstreamError) as caught:
                    await client.summary("character", "B", "Icecrown")
                assert caught.value.status == 503
            finally:
                release.set()
                await first
    asyncio.run(run())


@pytest.mark.parametrize("query,realm", [("", "Icecrown"), ("?realm=Blackrock", "Blackrock")])
def test_default_and_explicit_realm_forwarding(api, monkeypatch, query, realm):
    client, calls = api
    import warmane_api.main as routes
    seen = []

    async def overview(request, requested_realm, name, *options):
        seen.append((requested_realm, name))
        from fastapi.responses import JSONResponse
        return JSONResponse({"realm": requested_realm, "name": name})

    monkeypatch.setattr(routes, "character", overview)
    response = client.get("/api/v1/characters/Ahger" + query)
    assert response.status_code == 200
    assert seen == [(realm, "Ahger")]
    response = client.get("/api/v1/characters/Ahger/status" + query)
    assert response.status_code == 200
    assert f"character/Ahger/{realm}/summary" in calls[0]


@pytest.mark.parametrize("realm", ["", " Icecrown", "Icecrown ", "..", "a/b", "a?b", "a\\b"])
def test_invalid_query_realm_never_reaches_upstream(api, realm):
    client, calls = api
    for suffix in ("", "/status"):
        assert client.get("/api/v1/characters/Ahger" + suffix, params={"realm": realm}).status_code == 422
    assert calls == []


def test_character_only_public_schema(api):
    client, calls = api
    schema = client.get("/openapi.json").json()
    parameters = schema["paths"]["/api/v1/characters/{name}"]["get"]["parameters"]
    realm = next(p for p in parameters if p["name"] == "realm")
    assert realm["in"] == "query" and realm["schema"]["default"] == "Icecrown"
    assert not any("guilds" in path or path.endswith("/full") for path in schema["paths"])
    assert client.get("/api/v1/guilds/Icecrown/Test").status_code == 404
    assert calls == []
