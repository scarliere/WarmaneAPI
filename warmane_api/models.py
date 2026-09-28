"""Public response contracts for the primary character API."""
from typing import Any

from pydantic import BaseModel


class CharacterStatus(BaseModel):
    name: str
    realm: str
    online: bool | None
    observed_at: str
    cached: bool
    cache_ttl_seconds: float


class CharacterIdentity(BaseModel):
    name: str
    realm: str
    level: int | None = None
    faction: str | None = None
    gender: str | None = None
    race: str | None = None
    character_class: str | None = None
    guild: str | None = None
    achievement_points: int | None = None
    honorable_kills: int | None = None


class CharacterData(BaseModel):
    character: CharacterIdentity
    status: CharacterStatus
    stats: dict[str, Any] | None
    equipment: list[dict[str, Any]] | None
    professions: dict[str, Any]
    talent_builds: list[dict[str, Any]] | None
    glyphs: list[dict[str, Any]] | None
    collections: dict[str, Any] | None
    reputation: list[dict[str, Any]] | None
    achievements: dict[str, Any]
    statistics: dict[str, Any]
    pvp: dict[str, Any]


class Metadata(BaseModel):
    cached: bool
    fetched_at: str
    cache_ttl_seconds: float
    source: str = "warmane_json"
    source_url: str | None = None
    source_category: str | None = None
    source_parameters: dict[str, str] | None = None
    additional_sources: list[dict[str, Any]] | None = None


class Envelope(BaseModel):
    data: Any
    meta: Metadata


class ErrorDetail(BaseModel):
    code: str
    message: str
    upstream_error: Any = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class LookupError(ErrorDetail):
    status: int
    retry_after_seconds: int | None = None


class LookupMetadata(BaseModel):
    assembled_at: str
    complete: bool
    sources: dict[str, Metadata]
    errors: dict[str, LookupError]
    omitted: list[str]


class LookupResponse(BaseModel):
    data: dict[str, Any]
    meta: LookupMetadata


class CharacterMetadata(LookupMetadata):
    schema_version: str = "1.0"


class CharacterResponse(BaseModel):
    data: CharacterData
    meta: CharacterMetadata


class StatusResponse(BaseModel):
    data: CharacterStatus
    meta: Metadata


def status_data(summary, meta, realm):
    online = summary.get("online")
    return {"name": summary["name"], "realm": summary.get("realm", realm),
            "online": online if isinstance(online, bool) else None,
            "observed_at": meta["fetched_at"], "cached": meta["cached"],
            "cache_ttl_seconds": meta["cache_ttl_seconds"]}


def public_character(lookup, realm):
    """Project the internal combined result into a stable, grouped public schema."""
    data, meta = lookup["data"], lookup["meta"]
    summary = data["summary"]
    identity = {k: summary.get(k) for k in ("name", "level", "faction", "gender", "race", "guild")}
    identity.update(realm=summary.get("realm", realm), character_class=summary.get("class"),
                    achievement_points=summary.get("achievementpoints"), honorable_kills=summary.get("honorablekills"))
    equipment = data["equipment_details"]
    if equipment is not None:
        names = {item.get("item"): item.get("name") for item in summary.get("equipment", [])}
        equipment = [{**item, "name": names.get(item["item_id"])} for item in equipment]
    return {"data": {
        "character": identity,
        "status": status_data(summary, meta["sources"]["summary"], realm),
        "stats": data["stats"], "equipment": equipment,
        "professions": {"primary": data["profession_details"], "secondary": data["secondary_professions"]},
        "talent_builds": data["talent_builds"], "glyphs": data["glyphs"],
        "collections": data["collections"], "reputation": data["reputation"],
        "achievements": {**data["achievements"], "recent": data["recent_activity"]},
        "statistics": data["statistics"],
        "pvp": {"summary": data["pvp_summary"], "teams": summary.get("pvpteams"),
                "match_history": data["match_history"], "match_details": data["match_details"]},
    }, "meta": {**meta, "schema_version": "1.0"}}
