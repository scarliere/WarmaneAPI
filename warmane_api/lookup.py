"""Assemble character data through the existing, paced, cached source client."""
import asyncio
import time
from datetime import datetime, timezone

from .client import UpstreamError
from .normalize import normalize


async def full_character(client, name, realm, include_categories=False,
                         match_details_limit=0, match_details_offset=0, max_wait_seconds=120):
    if client.lookup_lock.locked():
        raise UpstreamError(503, "lookup_busy", "A combined lookup is already running; retry later.", retry_after=5)
    async with client.lookup_lock:
        return await _assemble(client, name, realm, include_categories,
                               match_details_limit, match_details_offset, max_wait_seconds)


async def _assemble(client, name, realm, include_categories, match_limit, match_offset, max_wait):
    deadline = time.monotonic() + max_wait
    sources, errors, omitted = {}, {}, []
    stopped = None

    async def collect(key, operation, required=False):
        nonlocal stopped
        try:
            if stopped:
                raise UpstreamError(503, "lookup_stopped", stopped)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            value, meta = await asyncio.wait_for(operation(), timeout=remaining)
            sources[key] = meta
            return value
        except TimeoutError:
            stopped = "Combined lookup time budget expired. Retry to reuse the sources already cached."
            error = UpstreamError(504, "lookup_timeout", stopped)
        except UpstreamError as exc:
            error = exc
            if exc.status == 503 or exc.code == "upstream_api_error":
                stopped = "Stopped after an upstream cooldown or API rejection. Respect retry_after_seconds."
        if required:
            raise error
        errors[key] = {"status": error.status, "code": error.code, "message": error.message,
                       "upstream_error": error.upstream_error, "retry_after_seconds": error.retry_after}
        return None

    def page(section, category=None):
        return lambda: client.page("character", name, realm, section, category, wait_for_budget=True)

    # A failed primary lookup must remain an HTTP error, not a successful empty character.
    summary = await collect("summary", lambda: client.summary("character", name, realm, wait_for_budget=True), required=True)
    data = {"summary": normalize(summary)}
    profile = await collect("profile", page("profile"))
    for field in ("stats", "secondary-professions", "profession-details", "equipment-details", "recent-activity", "pvp-summary"):
        data[field.replace("-", "_")] = profile[field] if profile is not None else None
    builds = await collect("talent_builds", page("talents"))
    data["talent_builds"] = builds
    data["glyphs"] = [{k: b[k] for k in ("spec_index", "active", "glyphs")} for b in builds] if builds is not None else None
    data["collections"] = await collect("collections", page("mounts-and-companions"))
    data["reputation"] = await collect("reputation", page("reputation"))
    for section in ("achievements", "statistics"):
        categories = await collect(section + ".categories", page(section))
        overview = await collect(section + ".summary", page(section, "summary"))
        expanded = None
        if include_categories:
            if categories is not None:
                expanded = {}
                # Parents and children can overlap; retain data per category rather
                # than silently dropping rows based on a guessed deduplication rule.
                for category in dict.fromkeys(c["id"] for c in categories if c["id"] != "summary"):
                    expanded[category] = await collect(section + ".categories." + category, page(section, category))
        else:
            omitted.append(section + ".by_category (set include_categories=true)")
        data[section] = {"summary": overview, "categories": categories, "by_category": expanded}
    history = await collect("match_history", page("match-history"))
    if history is not None:
        history = sorted(history, key=lambda m: m["start_timestamp"], reverse=True)
    data["match_history"] = history
    details = None
    if history is not None:
        ids = list(dict.fromkeys(m["match_id"] for m in history))
        chosen = ids[match_offset:match_offset + match_limit]
        details = {}
        for match_id in chosen:
            details[str(match_id)] = await collect("matches." + str(match_id),
                lambda mid=match_id: client.match(name, realm, mid, wait_for_budget=True))
        if len(chosen) != len(ids):
            omitted.append(f"match_details: selected {len(chosen)} of {len(ids)} unique matches; adjust match_details_limit/offset")
    data["match_details"] = details
    return {"data": data, "meta": {"assembled_at": datetime.now(timezone.utc).isoformat(),
            "complete": not errors, "sources": sources, "errors": errors, "omitted": omitted}}
