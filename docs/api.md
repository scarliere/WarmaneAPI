# Primary API contract (schema 1.0)

`GET /api/v1/characters/{name}?realm=Icecrown` performs an exact character lookup. It does not search account names or perform fuzzy matching. Encode path components with your HTTP library; spaces are `%20` in requests to this API.

Omit `realm` to use Icecrown. Explicit realm path URLs remain supported. The query parameter must be nonempty and have no surrounding whitespace or path separators.

The response always has `data` and `meta`. `data.character` contains `name`, `realm`, `level`, `faction`, `gender`, `race`, `character_class`, `guild`, `achievement_points` and `honorable_kills`. Source-specific masks and raw fields remain available via `/summary`.

`data.status` has this shape (illustrative values):

```json
{
  "name": "Sengtuary",
  "realm": "Icecrown",
  "online": false,
  "observed_at": "2026-09-23T00:00:00+00:00",
  "cached": true,
  "cache_ttl_seconds": 60.0
}
```

`GET /api/v1/characters/{name}/status?realm=Icecrown` returns this same object as `data`, with single-source metadata. It only needs the JSON summary. Use `online` as a three-state value: true, false or null (unknown). Fetch errors return HTTP errors; they are not mapped to false. Cached status may be up to the configured TTL old, plus Warmane's own update delay. There is no authoritative last-login field.

The overview includes:

- `stats`: displayed groups and names, e.g. `data.stats.Attributes.Strength`. Percentages and damage ranges remain strings.
- `equipment`: 19 layout slots with item IDs, names, quality, icon URL and observed enchant/gem codes. Names are joined by item ID, never array position. Empty slots have null item IDs/names. If the HTML profile fails, this section is null and `meta.errors.profile` explains why; the standalone summary still exposes its simpler equipment list.
- `professions`: `primary` and `secondary` skill arrays. An absent optional secondary section is an empty array (none listed), not proof the character has a zero skill.
- `talent_builds`, `glyphs`, `collections`, `reputation`: the parsed section shapes described in [extended endpoints](extended-api.md).
- `achievements`: `summary`, `categories`, optional `by_category`, and `recent` activity.
- `statistics`: `summary`, `categories`, optional `by_category`.
- `pvp`: `summary`, `teams`, all returned `match_history`, and requested `match_details`.

The default fetches overview data from ten unique sources. `include_categories=true` expands each listed achievement/statistic category. `match_details_limit` (0–100) and `match_details_offset` select a slice of unique matches for participant details. `max_wait_seconds` (1–900, default 120) caps the assembly time. These options have the same behavior as [the legacy combined route](archive/combined-lookup.md).

## Metadata and errors

`meta.schema_version` is `1.0`; `assembled_at` is the final assembly time. `sources` contains each source's URL, retrieval time, cache status and upstream parameters. Related fields share a source: status uses `summary`, while stats/equipment/professions use `profile`.

`meta.complete` means all requested sources succeeded, not that optional deep expansions were requested. Check `meta.omitted` for unrequested categories or match-detail slices. Source observations have independent fetch times and do not form an atomic snapshot.

If the primary summary fails, the route returns the standard error status. Other source failures return HTTP 200 with partial data, `meta.complete: false`, null affected sections, and `meta.errors` keyed by source. Never treat a partial result as a complete empty profile. The combined route stops further requests after rate limits/API rejection and cancels pending work at its deadline. Successful source results remain cached for subsequent calls.

| HTTP status | Meaning |
| --- | --- |
| 404 | Upstream explicitly returned 404 or route does not exist |
| 422 | Invalid input; standard FastAPI `detail` body |
| 502 | Network failure, upstream API error, unexpected response or HTML layout |
| 503 | Request budget or combined lookup busy; honor `Retry-After` |
| 504 | Upstream timeout or required lookup deadline exceeded |

Upstream errors use `{"error":{"code":"...","message":"...","upstream_error":null}}`. Unknown Warmane numeric codes are preserved without guessing their meanings. A misspelled realm can produce an unexpected upstream page and therefore 502; realm availability is not hardcoded.

## Compatibility

Version 0.3 changes the base character URL from a summary to the grouped overview. Old summary clients should use `/summary`; `raw=true` applies there. `/full` retains the previous `data.summary`, `data.equipment_details` and other legacy field locations. Individual character section routes remain available. Guild routes were removed in version 0.4. New integrations should use the base route and `/status`.
