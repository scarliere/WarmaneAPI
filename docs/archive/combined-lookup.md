# Legacy combined character lookup

```http
GET /api/v1/characters/Icecrown/Sengtuary/full
```

[Try Sengtuary](http://127.0.0.1:8000/api/v1/characters/Icecrown/Sengtuary/full) or use `/docs`. This compatibility endpoint is deprecated. New clients should use [the primary character route](../api.md). The old JSON summary is now at `/summary`; individual-section routes retain their behavior.

```bash
curl --max-time 130 \
  'http://127.0.0.1:8000/api/v1/characters/Icecrown/Sengtuary/full'
```

The response has `data` and `meta`. Data keys:

| Key | Contents |
| --- | --- |
| `summary` | Normalized character JSON, including name, level, online status, equipment, professions, talents, guild and PvP teams |
| `stats` | Attributes, Melee, Ranged, Defense, Spell and Resistances |
| `equipment_details` | All 19 layout slots with observed item IDs, quality, enchant/gem codes and icons |
| `profession_details`, `secondary_professions` | Listed skills and current/maximum values |
| `recent_activity`, `pvp_summary` | Recent achievements and displayed kill counters |
| `talent_builds`, `glyphs` | Separate specs, tree/node ranks and glyphs |
| `collections`, `reputation` | Mounts, companions and faction standings |
| `achievements` | `summary`, category index, optional `by_category` data |
| `statistics` | `summary`, category index, optional `by_category` data |
| `match_history` | All returned history rows, newest first; no default pagination truncation |
| `match_details` | Requested participant details keyed by match ID |

For example, read Strength at `data.stats.Attributes.Strength` and equipped items at `data.equipment_details`. Data shapes inside each section match the [extended API guide](../extended-api.md). Guild-wide roster/ranks and boss fights remain separate endpoints; the character's guild name is in `data.summary.guild`.

## Optional deeper data

| Query parameter | Default | Meaning |
| --- | --- | --- |
| `include_categories` | `false` | Fetch every distinct non-summary category ID listed on the achievement/statistics pages |
| `match_details_limit` | `0` | Fetch participant details for up to this many unique matches, newest first; 0–100 |
| `match_details_offset` | `0` | Skip this many unique matches before fetching details; nonnegative |
| `max_wait_seconds` | `120` | Overall lookup deadline, including pacing and network time; 1–900 |

```bash
curl --max-time 910 \
  'http://127.0.0.1:8000/api/v1/characters/Icecrown/Sengtuary/full?include_categories=true&match_details_limit=100&max_wait_seconds=900'
```

The default gathers every character overview from ten unique sources. It does **not** fetch every achievement/statistic category or every historical match's participant list. Those expansions can require hundreds of additional requests on some characters. When disabled, `by_category` is null; when enabled, it is keyed by category ID, preserving potentially overlapping parent/child results. If the category index fails, `by_category` is also null and the failure is recorded.

`match_details` is an object keyed by requested match IDs, or null if history could not be retrieved. For an empty history it is `{}`. If details are not requested or only a slice is requested, `meta.omitted` states how many matches were selected out of the available unique IDs. Use the limit/offset options or the standalone `/matches/{match_id}` route to retrieve more.

## Timing, caching and failure behavior

A cold default lookup generally needs 40–60 seconds at the default four-second upstream interval, but network conditions can increase this. Detailed category expansion takes several minutes. Set client/proxy timeouts above `max_wait_seconds`. No third-party scripts are executed.

Each source uses the existing cache and shared request budget. Profile-backed fields need one HTML fetch; glyphs and talent builds share another. The combined route waits between requests rather than returning a 503 for its own routine pacing. Individual routes still fail fast when the upstream budget is busy. Only one combined lookup per process is allowed at a time; a second returns 503 `lookup_busy` with `Retry-After: 5`.

Metadata:

- `assembled_at`: when assembly finished; the sources do not form an atomic snapshot.
- `complete`: all **requested** sources succeeded. This does not imply optional expansions were requested.
- `sources`: per-source URLs, fetch timestamps, cache flags and upstream parameters. Shared profile fields reference the `profile` entry; glyphs share `talent_builds`.
- `errors`: failures keyed by source, with status, code, message and optional `retry_after_seconds`.
- `omitted`: data intentionally outside the requested expansion/slice.

If the initial character summary fails, the route returns the normal HTTP error. If another source fails, successfully fetched sections are kept and the route returns HTTP 200 with `meta.complete: false`; affected fields are null. A local deadline cancels the current fetch and skips later sources. An upstream rate limit/API rejection stops further source requests rather than continuing to hammer Warmane. Inspect the named error and its retry delay before retrying.

Only successful individual sources are cached, not the assembled response. A repeated lookup can reuse those results and recover failed sections. This also works when cache reuse is disabled: the assembler retains each source in the current response and does not refetch it to build related views.
