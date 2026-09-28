import asyncio
import json
from pathlib import Path

import httpx
import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from warmane_api.client import UpstreamError, WarmaneClient
from warmane_api.main import app
from warmane_api.parsers import parse_page, match_details

FIXTURES = Path(__file__).parent / "fixtures" / "live"


def read(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def parse(section, character="Sengtuary", realm="Icecrown", prefix="sengtuary"):
    return parse_page(section, read(f"{prefix}-{section}.html"), character, realm)


def test_sengtuary_profile_slots_stats_and_missing_secondary_skills():
    result = parse("profile")
    assert result["stats"]["Attributes"]["Strength"] == 2258
    assert result["secondary-professions"] == []  # Absence is not a zero skill level.
    assert result["profession-details"] == [
        {"name": "Mining", "skill": 7, "maximum": 75},
        {"name": "Jewelcrafting", "skill": 1, "maximum": 75}]
    equipment = {i["slot"]: i for i in result["equipment-details"]}
    assert len(equipment) == 19
    assert equipment["head"]["item_id"] == 51162
    assert equipment["head"]["enchant_code"] == 3817
    assert equipment["head"]["gem_codes"] == [3628, 3518, 0]
    assert equipment["shirt"]["item_id"] == 45664
    assert equipment["off_hand"]["item_id"] is None
    assert equipment["tabard"]["item_id"] is None
    assert equipment["main_hand"]["item_id"] == 51936
    summary = json.loads(read("sengtuary-summary.json"))
    assert {i["item_id"] for i in equipment.values() if i["item_id"]} == {int(i["item"]) for i in summary["equipment"]}


def test_sengtuary_dual_specs_and_glyphs_stay_separate():
    specs = parse("talents")
    assert [s["active"] for s in specs] == [False, True]
    assert [[t["points"] for t in s["trees"]] for s in specs] == [[0, 56, 15], [11, 5, 55]]
    assert [len(s["glyphs"]) for s in specs] == [6, 6]
    assert all(sum(t["points"] for t in s["trees"]) == 71 for s in specs)
    assert specs[0]["glyphs"] != specs[1]["glyphs"]


def test_druid_single_spec_and_secondary_professions():
    # Independent class and single-spec samples from the earlier investigation.
    profile = read("dojun-profile.html")
    talents = read("dojun-talents.html")
    data = parse_page("profile", profile, "Dojun", "Icecrown")
    assert data["secondary-professions"] == [{"name": "First Aid", "skill": 376, "maximum": 450},
                                              {"name": "Fishing", "skill": 192, "maximum": 225}]
    specs = parse_page("talents", talents, "Dojun", "Icecrown")
    assert len(specs) == 1 and specs[0]["active"] is None
    assert [t["points"] for t in specs[0]["trees"]] == [58, 0, 13]


def test_empty_professions_and_empty_equipment_preserve_slots():
    soup = BeautifulSoup(read("sengtuary-profile.html"), "html.parser")
    for stub in soup.select(".profskills .stub"):
        stub.decompose()
    slot = soup.select_one(".item-left .item-slot")
    slot.clear()
    slot.append(BeautifulSoup('<div class="icon-quality tooltip" data-tooltip="Head"><a href="#self"></a></div>', "html.parser"))
    result = parse_page("profile", str(soup), "Sengtuary", "Icecrown")
    assert result["profession-details"] == []
    assert result["equipment-details"][0]["item_id"] is None
    assert result["equipment-details"][1]["slot"] == "neck"


def test_cross_realm_profile_and_populated_matches():
    result = parse("profile", "Cowysparttwo", "Blackrock", "blackrock")
    assert result["secondary-professions"][0]["skill"] == 450
    assert len(parse("talents", "Cowysparttwo", "Blackrock", "blackrock")) == 2
    matches = parse("match-history", "Cowysparttwo", "Blackrock", "blackrock")
    assert len(matches) == 1509
    assert matches[0]["match_id"] == 31806864
    assert matches[0]["start_timestamp"] == 1728159312
    assert parse("match-history") == []


def test_match_details_strip_markup_and_keep_ids_distinct_from_masks():
    data = match_details(json.loads(read("blackrock-match-details.json")), "Cowysparttwo", "Blackrock")
    player = next(p for p in data if p["name"] == "Cowysparttwo")
    assert player["class_id"] == 2
    assert player["healing_done"] == 126490
    assert player["personal_rating"] == "999 ( -1 )"
    assert "<span" not in json.dumps(data)
    with pytest.raises(ValueError):
        match_details(json.loads(read("blackrock-match-details.json")), "Sengtuary", "Icecrown")


def test_achievements_and_statistics_categories_and_values():
    summary = parse_page("achievements", json.loads(read("sengtuary-achievement-summary.json"))["content"], "Sengtuary", "Icecrown", "summary")
    assert summary["completed"] == 162 and summary["total"] == 1058
    assert summary["categories"][-1] == {"name": "Feats of Strength", "completed": 1, "total": None}
    data = parse_page("achievements", json.loads(read("sengtuary-achievement-general.json"))["content"], "Sengtuary", "Icecrown", "92")
    assert len(data["achievements"]) == 55
    assert sum(a["earned"] for a in data["achievements"]) == 24
    assert data["achievements"][0]["date_text"] == "Earned 06/28/2026"
    assert data["achievements"][0]["criteria_text"] is None
    assert data["achievements"][-1]["reward"] == "Reward: Red Dragonhawk Mount"
    stats = parse_page("statistics", json.loads(read("sengtuary-statistics-summary.json"))["content"], "Sengtuary", "Icecrown", "summary")
    lookup = {s["description"]: s for s in stats["statistics"]}
    assert lookup["Quests completed"]["value"] == 418
    assert lookup["Professions learned"]["value"] is None
    assert any(c["id"] == "92" for c in parse("achievements"))
    assert any(c["parent_id"] is not None for c in parse("statistics"))


def test_collections_and_reputation():
    collections = parse("mounts-and-companions")
    assert len(collections["mounts"]) == 4
    assert collections["mounts"][0]["item_id"] == 25475
    assert any(r["is_exalted_placeholder"] for r in parse("reputation"))


@pytest.mark.parametrize("section,prefix,selector", [
    ("profile", "sengtuary", ".character-stats"),
    ("profile", "sengtuary", ".item-left .item-slot"),
    ("talents", "sengtuary", ".talent-tree-info"),
    ("mounts-and-companions", "sengtuary", "#mount-tab"),
    ("reputation", "sengtuary", ".reputation .standing"),
    ("match-history", "sengtuary", "thead"),
])
def test_markup_drift_fails_instead_of_silently_returning_empty(section, prefix, selector):
    soup = BeautifulSoup(read(f"{prefix}-{section}.html"), "html.parser")
    soup.select_one(selector).decompose()
    with pytest.raises(ValueError):
        parse_page(section, str(soup), "Sengtuary", "Icecrown")


@pytest.mark.parametrize("markup,name,realm", [
    ("<html>Checking your browser</html>", "Sengtuary", "Icecrown"),
    (None, "Someoneelse", "Icecrown"), (None, "Sengtuary", "Lordaeron"),
])
def test_challenge_or_wrong_identity_rejected(markup, name, realm):
    with pytest.raises(ValueError):
        parse_page("profile", markup or read("sengtuary-profile.html"), name, realm)


@pytest.fixture
def api():
    calls = []
    def handler(request):
        calls.append(request)
        path = request.url.path
        if path.startswith("/api/"):
            summary = json.loads(read("sengtuary-summary.json"))
            if "/Blackrock/" in path:
                summary.update(name="Cowysparttwo", realm="Blackrock")
            return httpx.Response(200, json=summary)
        section = path.rsplit("/", 1)[1]
        if request.method == "POST":
            form = request.content.decode()
            if "matchinfo=" in form:
                return httpx.Response(200, json=json.loads(read("blackrock-match-details.json")))
            filename = "sengtuary-statistics-summary.json" if section == "statistics" else (
                "sengtuary-achievement-general.json" if form == "category=92" else "sengtuary-achievement-summary.json")
            return httpx.Response(200, json=json.loads(read(filename)))
        prefix = "blackrock" if "/Blackrock/" in path else "sengtuary"
        if prefix == "blackrock" and not (FIXTURES / f"{prefix}-{section}.html").exists():
            # Synthetic coverage for the combined lookup; only profile, talents
            # and history are live Blackrock fixtures.
            markup = read(f"sengtuary-{section}.html").replace("Sengtuary", "Cowysparttwo").replace("Icecrown", "Blackrock")
            return httpx.Response(200, text=markup)
        return httpx.Response(200, text=read(f"{prefix}-{section}.html"))
    with TestClient(app) as client:
        app.state.warmane = WarmaneClient(httpx.AsyncClient(base_url="https://armory.warmane.com/api/",
            transport=httpx.MockTransport(handler)), interval=0)
        yield client, calls
        client.portal.call(app.state.warmane.http.aclose)


@pytest.mark.parametrize("section", ["stats", "secondary-professions", "profession-details", "equipment-details",
    "recent-activity", "pvp-summary", "talent-builds", "glyphs", "reputation", "collections",
    "achievement-summary", "achievements", "achievement-categories", "statistics", "statistic-categories", "match-history"])
def test_all_new_character_views(api, section):
    client, _ = api
    response = client.get(f"/api/v1/characters/Icecrown/Sengtuary/{section}")
    assert response.status_code == 200, response.text
    assert response.json()["meta"]["source"].startswith("warmane_")
    assert response.json()["meta"]["source_url"].startswith("https://armory.warmane.com/character/")


def test_related_views_share_cache_but_categories_do_not(api):
    client, calls = api
    base = "/api/v1/characters/Icecrown/Sengtuary/"
    assert client.get(base + "stats").status_code == 200
    assert client.get(base + "equipment-details").json()["meta"]["cached"]
    assert len(calls) == 1
    client.get(base + "talent-builds")
    assert client.get(base + "glyphs").json()["meta"]["cached"]
    client.get(base + "achievement-summary")
    summary = client.get(base + "achievements").json()
    assert summary["meta"]["cached"]
    general = client.get(base + "achievements?category=92").json()
    assert not general["meta"]["cached"]
    assert general["data"]["category"] == "92"
    assert general["meta"]["source_parameters"] == {"category": "92"}
    assert calls[-1].method == "POST" and calls[-1].content == b"category=92"
    before = len(calls)
    assert client.get(base + "statistics?category=../bad").status_code == 422
    assert len(calls) == before


def test_history_pagination_and_match_details(api):
    client, _ = api
    base = "/api/v1/characters/Blackrock/Cowysparttwo"
    page = client.get(base + "/match-history?offset=1&limit=2").json()["data"]
    assert page["total"] == 1509 and len(page["matches"]) == 2
    assert page["matches"][0]["start_timestamp"] >= page["matches"][1]["start_timestamp"]
    details = client.get(base + "/matches/31806864").json()
    assert len(details["data"]) == 4
    assert details["meta"]["source_parameters"] == {"matchinfo": "31806864"}


def test_json_and_html_share_budget_and_invalid_markup_is_not_cached():
    async def run():
        def handler(request):
            if "/api/" in request.url.path:
                return httpx.Response(200, json=json.loads(read("sengtuary-summary.json")))
            return httpx.Response(200, text="<html>Unexpected login page</html>")
        async with httpx.AsyncClient(base_url="https://armory.warmane.com/api/", transport=httpx.MockTransport(handler)) as http:
            client = WarmaneClient(http, interval=4)
            await client.summary("character", "Sengtuary", "Icecrown")
            with pytest.raises(UpstreamError) as busy:
                await client.page("character", "Sengtuary", "Icecrown", "profile")
            assert busy.value.status == 503
            client.next_request = 0
            with pytest.raises(UpstreamError) as invalid:
                await client.page("character", "Sengtuary", "Icecrown", "profile")
            assert invalid.value.status == 502
            assert len(client.cache) == 1
    asyncio.run(run())


def test_parse_error_uses_api_error_envelope():
    with TestClient(app) as client:
        app.state.warmane = WarmaneClient(httpx.AsyncClient(base_url="https://armory.warmane.com/api/",
            transport=httpx.MockTransport(lambda _: httpx.Response(200, text="<html>Challenge</html>"))), interval=0)
        response = client.get("/api/v1/characters/Icecrown/Sengtuary/stats")
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "invalid_upstream_response"
        assert not app.state.warmane.cache
        client.portal.call(app.state.warmane.http.aclose)


def test_http_date_retry_after_is_honored():
    from datetime import datetime, timedelta, timezone
    from email.utils import format_datetime
    async def run():
        header = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=120), usegmt=True)
        async with httpx.AsyncClient(base_url="https://armory.warmane.com/api/", transport=httpx.MockTransport(
            lambda _: httpx.Response(429, headers={"Retry-After": header}))) as http:
            with pytest.raises(UpstreamError) as caught:
                await WarmaneClient(http).summary("character", "Sengtuary", "Icecrown")
            assert 115 <= caught.value.retry_after <= 120
    asyncio.run(run())


def test_combined_lookup_contains_stats_and_reuses_ten_sources(api):
    client, calls = api
    base = "/api/v1/characters/Icecrown/Sengtuary"
    response = client.get(base + "/full")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["data"]["summary"]["name"] == "Sengtuary"
    assert body["data"]["stats"]["Attributes"]["Strength"] == 2258
    assert body["data"]["summary"]["equipment"][0]["item"] == 51162
    assert len(body["data"]["equipment_details"]) == 19
    assert len(body["data"]["glyphs"]) == 2
    assert body["data"]["achievements"]["summary"]["completed"] == 162
    assert body["data"]["match_history"] == [] and body["data"]["match_details"] == {}
    assert body["meta"]["complete"] and body["meta"]["errors"] == {}
    assert len(body["meta"]["sources"]) == len(calls) == 10
    assert len(body["meta"]["omitted"]) == 2
    repeated = client.get(base + "/full").json()
    assert all(s["cached"] for s in repeated["meta"]["sources"].values())
    assert len(calls) == 10
    assert client.get(base + "/stats").json()["meta"]["cached"]
    assert len(calls) == 10


def test_combined_lookup_paces_cold_sources(api):
    import time
    client, _ = api
    starts = []
    async def record(request):
        starts.append(time.monotonic())
    app.state.warmane.http.event_hooks["request"] = [record]
    app.state.warmane.interval = 0.03
    assert client.get("/api/v1/characters/Icecrown/Sengtuary/full").json()["meta"]["complete"]
    assert len(starts) == 10
    assert all(b - a >= 0.025 for a, b in zip(starts, starts[1:]))


def test_combined_lookup_reports_partial_failure_and_continues(api, monkeypatch):
    client, _ = api
    original = app.state.warmane.page
    async def fail_reputation(kind, name, realm, section, category=None, **kwargs):
        if section == "reputation":
            raise UpstreamError(502, "invalid_upstream_response", "Unexpected markup")
        return await original(kind, name, realm, section, category, **kwargs)
    monkeypatch.setattr(app.state.warmane, "page", fail_reputation)
    response = client.get("/api/v1/characters/Icecrown/Sengtuary/full")
    assert response.status_code == 200
    body = response.json()
    assert not body["meta"]["complete"]
    assert body["meta"]["errors"]["reputation"]["status"] == 502
    assert body["data"]["reputation"] is None
    assert body["data"]["stats"]["Attributes"]["Strength"] == 2258
    assert body["data"]["statistics"]["summary"]["statistics"]


def test_combined_lookup_expands_requested_categories_and_matches(api, monkeypatch):
    client, _ = api
    original = app.state.warmane.page
    async def limited_categories(kind, name, realm, section, category=None, **kwargs):
        result, meta = await original(kind, name, realm, section, category, **kwargs)
        if section in {"achievements", "statistics"} and category is None:
            result = [{"id": "summary"}, {"id": "92" if section == "achievements" else "130"}]
        return result, meta
    monkeypatch.setattr(app.state.warmane, "page", limited_categories)
    base = "/api/v1/characters/Blackrock/Cowysparttwo/full"
    response = client.get(base + "?include_categories=true&match_details_limit=1&match_details_offset=1508")
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["achievements"]["by_category"]["92"]["achievements"][0]["achievement_id"] == 6
    assert data["statistics"]["by_category"]["130"]["category"] == "130"
    assert len(data["match_history"]) == 1509
    assert "31806864" in data["match_details"]
    assert len(data["match_details"]["31806864"]) == 4
    assert any("1 of 1509" in x for x in response.json()["meta"]["omitted"])


def test_combined_lookup_stops_after_rate_limit(api, monkeypatch):
    client, calls = api
    async def rate_limited(*args, **kwargs):
        raise UpstreamError(503, "upstream_rate_limited", "Rate limited", retry_after=60)
    monkeypatch.setattr(app.state.warmane, "page", rate_limited)
    result = client.get("/api/v1/characters/Icecrown/Sengtuary/full").json()
    assert result["meta"]["errors"]["profile"]["retry_after_seconds"] == 60
    assert result["meta"]["errors"]["talent_builds"]["code"] == "lookup_stopped"
    assert len(calls) == 1


def test_combined_lookup_deadline_returns_partial_and_releases_lock(api, monkeypatch):
    client, _ = api
    original = app.state.warmane.page
    async def slow(*args, **kwargs):
        await asyncio.sleep(2)
        return await original(*args, **kwargs)
    monkeypatch.setattr(app.state.warmane, "page", slow)
    result = client.get("/api/v1/characters/Icecrown/Sengtuary/full?max_wait_seconds=1").json()
    assert result["data"]["summary"]["name"] == "Sengtuary"
    assert result["meta"]["errors"]["profile"]["code"] == "lookup_timeout"
    assert not app.state.warmane.lookup_lock.locked()


def test_combined_lookup_required_failure_busy_and_validation(api, monkeypatch):
    client, calls = api
    path = "/api/v1/characters/Icecrown/Sengtuary/full"
    assert client.get(path + "?match_details_limit=101").status_code == 422
    assert client.get(path + "?max_wait_seconds=0").status_code == 422
    assert client.get("/api/v1/characters/Icecrown/%20/full").status_code == 422
    client.portal.call(app.state.warmane.lookup_lock.acquire)
    try:
        assert client.get(path).json()["error"]["code"] == "lookup_busy"
    finally:
        client.portal.call(app.state.warmane.lookup_lock.release)
    async def missing(*args, **kwargs):
        raise UpstreamError(404, "not_found", "Not found")
    monkeypatch.setattr(app.state.warmane, "summary", missing)
    assert client.get(path).status_code == 404
    assert not calls


@pytest.mark.parametrize("path", ["/api/v1/characters/Sengtuary", "/api/v1/characters/Icecrown/Sengtuary"])
def test_primary_character_contract_and_status(api, path):
    client, calls = api
    response = client.get(path)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"]["schema_version"] == "1.0"
    assert body["meta"]["complete"]
    assert body["data"]["character"]["name"] == "Sengtuary"
    assert body["data"]["character"]["character_class"] == "Paladin"
    assert body["data"]["character"]["achievement_points"] == 1690
    assert body["data"]["status"]["online"] is False
    assert body["data"]["status"]["observed_at"] == body["meta"]["sources"]["summary"]["fetched_at"]
    assert body["data"]["stats"]["Attributes"]["Strength"] == 2258
    assert body["data"]["equipment"][0]["name"] == "Sanctified Lightsworn Helmet"
    assert body["data"]["equipment"][6]["name"] is None
    assert body["data"]["professions"]["primary"][0]["name"] == "Mining"
    assert body["data"]["pvp"]["match_history"] == []
    status = client.get(path + "/status").json()
    assert status["data"]["cached"] and status["data"]["online"] is False
    assert len(calls) == 10
    schema = client.get("/openapi.json").json()
    assert "CharacterData" in schema["components"]["schemas"]
    assert "stats" in schema["components"]["schemas"]["CharacterData"]["properties"]


def test_primary_partial_data_keeps_status_and_errors(api, monkeypatch):
    client, _ = api
    original = app.state.warmane.page
    async def fail_profile(kind, name, realm, section, category=None, **kwargs):
        if section == "profile":
            raise UpstreamError(502, "invalid_upstream_response", "Unexpected markup")
        return await original(kind, name, realm, section, category, **kwargs)
    monkeypatch.setattr(app.state.warmane, "page", fail_profile)
    response = client.get("/api/v1/characters/Icecrown/Sengtuary")
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"]["online"] is False
    assert body["data"]["stats"] is None and body["data"]["equipment"] is None
    assert not body["meta"]["complete"] and "profile" in body["meta"]["errors"]
