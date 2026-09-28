import math
import os
from contextlib import asynccontextmanager
from typing import Annotated, Literal

import httpx
from fastapi import FastAPI, Path, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from .client import UpstreamError, WarmaneClient
from .normalize import normalize
from .lookup import full_character
from .models import (CharacterResponse, Envelope, ErrorResponse, LookupResponse, StatusResponse,
                     public_character, status_data)



def setting(name, default, minimum=0):
    value = float(os.getenv(name, default))
    if not math.isfinite(value) or value < minimum:
        raise ValueError(f"{name} must be finite and >= {minimum}")
    return value


@asynccontextmanager
async def lifespan(app):
    async with httpx.AsyncClient(
        base_url="https://armory.warmane.com/api/",
        timeout=setting("WARMANE_TIMEOUT_SECONDS", "15", 0.1),
        follow_redirects=False,
        headers={"Accept": "application/json, text/html;q=0.9", "User-Agent": "WarmaneAPI/0.4"},
    ) as http:
        app.state.warmane = WarmaneClient(
            http, ttl=setting("WARMANE_CACHE_TTL_SECONDS", "60"),
            interval=setting("WARMANE_MIN_INTERVAL_SECONDS", "4"),
            html_ttl=setting("WARMANE_HTML_CACHE_TTL_SECONDS", "300"),
        )
        yield


app = FastAPI(
    title="Warmane Character API", version="0.4.0", lifespan=lifespan,
    description="Look up a character by realm and name for combined data, or use /status for lightweight status polling. "
                "Fields depend on Warmane; see README for normalization and limitations.",
    responses={status: {"model": ErrorResponse} for status in (404, 502, 503, 504)},
)
origins = [s.strip() for s in os.getenv("CORS_ORIGINS", "").split(",") if s.strip()]
if origins:
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET"],
                       allow_headers=["Accept"], expose_headers=["Retry-After"])


@app.exception_handler(UpstreamError)
async def upstream_error(request: Request, exc: UpstreamError):
    headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else {}
    return JSONResponse(status_code=exc.status, headers=headers, content={"error": {
        "code": exc.code, "message": exc.message, "upstream_error": exc.upstream_error,
    }})


Segment = Annotated[str, Path(min_length=1, max_length=100, pattern=r"^[^/\\?#%\x00-\x1f\x7f]+$",
                             description="Exact name; URL-encode spaces as %20. Do not substitute +.")]


def validate_names(realm, name):
    if name.strip() != name or realm.strip() != realm or name in {".", ".."} or realm in {".", ".."}:
        from fastapi import HTTPException
        raise HTTPException(422, "Names must not have surrounding whitespace or be dot segments.")


async def fetch(request, kind, realm, name, raw=False):
    validate_names(realm, name)
    data, meta = await request.app.state.warmane.summary(kind, name, realm)
    return {"data": data if raw else normalize(data), "meta": meta}


async def fetch_page(request, kind, realm, name, section, category=None):
    validate_names(realm, name)
    data, meta = await request.app.state.warmane.page(kind, name, realm, section, category)
    return {"data": data, "meta": meta}


CharacterSection = Literal["equipment", "talents", "professions", "pvpteams",
    "stats", "secondary-professions", "profession-details", "equipment-details", "recent-activity",
    "pvp-summary", "talent-builds", "glyphs", "reputation", "collections", "achievement-summary",
    "achievements", "achievement-categories", "statistics", "statistic-categories", "match-history"]
Category = Annotated[str, Query(pattern=r"^(summary|[1-9][0-9]{0,5})$",
                                description="For achievements/statistics only: summary or a category ID from its categories endpoint.")]


@app.get("/health", tags=["Service"])
async def health():
    """Process liveness only; does not contact Warmane."""
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/docs")


RealmQuery = Annotated[str, Query(min_length=1, max_length=100,
    pattern=r"^[^/\\?#%\x00-\x1f\x7f]+$", description="Character realm; defaults to Icecrown.")]


@app.get("/api/v1/characters/{name}", response_model=CharacterResponse, tags=["Characters"],
         summary="Look up a character (Icecrown by default)")
async def lookup_character(request: Request, name: Segment, realm: RealmQuery = "Icecrown",
                           include_categories: bool = False,
                           match_details_limit: Annotated[int, Query(ge=0, le=100)] = 0,
                           match_details_offset: Annotated[int, Query(ge=0)] = 0,
                           max_wait_seconds: Annotated[int, Query(ge=1, le=900)] = 120):
    """Combined character data. Inspect meta.complete and meta.errors for partial results."""
    return await character(request, realm, name, include_categories, match_details_limit,
                           match_details_offset, max_wait_seconds)


@app.get("/api/v1/characters/{name}/status", response_model=StatusResponse, tags=["Characters"])
async def lookup_status(request: Request, name: Segment, realm: RealmQuery = "Icecrown"):
    """Lightweight online status; defaults to Icecrown. No current location is available."""
    return await character_status(request, realm, name)


@app.get("/api/v1/characters/{realm}/{name}/summary", response_model=Envelope, tags=["Character sections"])
async def character_summary(request: Request, realm: Segment, name: Segment, raw: bool = False):
    """Character summary. raw=true preserves upstream fields and types inside data."""
    return await fetch(request, "character", realm, name, raw)


@app.get("/api/v1/characters/{realm}/{name}", response_model=CharacterResponse, tags=["Characters"],
         summary="Look up a character with all overview data")
async def character(request: Request, realm: Segment, name: Segment,
                    include_categories: bool = False,
                    match_details_limit: Annotated[int, Query(ge=0, le=100)] = 0,
                    match_details_offset: Annotated[int, Query(ge=0)] = 0,
                    max_wait_seconds: Annotated[int, Query(ge=1, le=900)] = 120):
    """Primary lookup: character, status, stats, named equipment, professions,
    builds, glyphs, achievements, statistics, collections, reputation and PvP.
    Cold calls take about 40–60 seconds. Check meta.complete/errors for partial data.
    Category expansion and match participant details are opt-in.
    """
    validate_names(realm, name)
    result = await full_character(request.app.state.warmane, name, realm, include_categories,
                                 match_details_limit, match_details_offset, max_wait_seconds)
    return public_character(result, realm)


@app.get("/api/v1/characters/{realm}/{name}/status", response_model=StatusResponse, tags=["Characters"])
async def character_status(request: Request, realm: Segment, name: Segment):
    """Lightweight status check. online=null means unknown; observed_at is our fetch time.
    Cached status can be up to the configured JSON cache TTL old, plus Warmane's own delay.
    Upstream failures return errors, never a fabricated offline status.
    """
    result = await fetch(request, "character", realm, name)
    result["data"] = status_data(result["data"], result["meta"], realm)
    return result


@app.get("/api/v1/characters/{realm}/{name}/full", response_model=LookupResponse, tags=["Compatibility"], deprecated=True, include_in_schema=False)
async def character_full(request: Request, realm: Segment, name: Segment,
                         include_categories: bool = False,
                         match_details_limit: Annotated[int, Query(ge=0, le=100)] = 0,
                         match_details_offset: Annotated[int, Query(ge=0)] = 0,
                         max_wait_seconds: Annotated[int, Query(ge=1, le=900)] = 120):
    """Combined character lookup, including the full stat breakdown.

    Uses ten unique source requests on a cold default lookup, paced automatically.
    All available history rows are included. Category expansion and match participant
    details are opt-in. Set max_wait_seconds up to 900 for large expansions.
    A failed summary is an HTTP error. Other failures return HTTP 200 with
    meta.complete=false, named errors, and null affected sections. Inspect meta.omitted
    for data outside the requested scope. Guild endpoints are not fetched.
    """
    validate_names(realm, name)
    return await full_character(request.app.state.warmane, name, realm, include_categories,
                                match_details_limit, match_details_offset, max_wait_seconds)


@app.get("/api/v1/characters/{realm}/{name}/{section}", response_model=Envelope, tags=["Character sections"])
async def character_section(request: Request, realm: Segment, name: Segment,
                            section: CharacterSection, category: Category = "summary",
                            offset: Annotated[int, Query(ge=0)] = 0,
                            limit: Annotated[int, Query(ge=1, le=500)] = 100):
    """Summary fields and HTML-derived character views. See meta.source for provenance.

    Profile views share one page; talent-builds and glyphs share another.
    Achievements/statistics accept category=summary or a numeric category ID.
    Missing summary fields are null. HTML structure mismatches return 502.
    """
    if section in {"stats", "secondary-professions", "profession-details", "equipment-details", "recent-activity", "pvp-summary"}:
        result = await fetch_page(request, "character", realm, name, "profile")
        result["data"] = result["data"][section]
        return result
    if section in {"talent-builds", "glyphs"}:
        result = await fetch_page(request, "character", realm, name, "talents")
        if section == "glyphs":
            result["data"] = [{k: spec[k] for k in ("spec_index", "active", "glyphs")} for spec in result["data"]]
        return result
    if section in {"reputation", "collections", "match-history", "achievement-categories", "statistic-categories"}:
        page = {"collections": "mounts-and-companions", "achievement-categories": "achievements",
                "statistic-categories": "statistics"}.get(section, section)
        result = await fetch_page(request, "character", realm, name, page)
        if section == "match-history":
            matches = sorted(result["data"], key=lambda m: m["start_timestamp"], reverse=True)
            result["data"] = {"matches": matches[offset:offset + limit], "total": len(matches), "offset": offset, "limit": limit}
        return result
    if section in {"achievement-summary", "achievements", "statistics"}:
        return await fetch_page(request, "character", realm, name,
                                "statistics" if section == "statistics" else "achievements",
                                "summary" if section == "achievement-summary" else category)
    result = await fetch(request, "character", realm, name)
    data = result["data"]
    result["data"] = data.get(section)
    return result


@app.get("/api/v1/characters/{realm}/{name}/matches/{match_id}", response_model=Envelope, tags=["Characters"])
async def match(request: Request, realm: Segment, name: Segment,
                match_id: Annotated[int, Path(gt=0, le=2147483647)]):
    """Participants, damage, healing and rating changes for an ID from match-history."""
    validate_names(realm, name)
    data, meta = await request.app.state.warmane.match(name, realm, match_id)
    return {"data": data, "meta": meta}
