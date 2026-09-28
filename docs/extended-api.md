# Extended armory endpoints

All wrapper routes use GET and return `{"data": ..., "meta": ...}`. They require no account credentials. Interactive docs: `/docs`; OpenAPI: `/openapi.json`. For server startup and configuration see [README](../README.md).

To combine these character views into one response, use `/api/v1/characters/{name}?realm=Icecrown`. It places the stat breakdown at `data.stats`. See the [primary API contract](api.md) for expansion options, pacing, and partial-result metadata.

Use `/api/v1/characters/Icecrown/Sengtuary/` before the character suffixes below. Names are case-sensitive upstream; use exact spellings and encode spaces as `%20`. Public HTML is more fragile than a versioned JSON API: missing required markup or mismatched character/realm returns 502, with no cached failure.

## Profile views

`stats`, `secondary-professions`, `profession-details`, `equipment-details`, `recent-activity` and `pvp-summary` reuse one cached profile fetch (default 300 seconds).

- `stats`: object keyed by displayed group and stat names, e.g. `{"Attributes":{"Strength":2258},"Melee":{"Critical":"40.78%"}}`. Plain numbers become numbers; percentages, damage ranges and other compound display strings remain strings. Values are reported as displayed, including surprising zeros.
- `profession-details` and `secondary-professions`: arrays of `{"name":"Mining","skill":7,"maximum":75}`. An absent optional secondary-skills section means `[]` (none listed), not a zero skill for every profession. Sengtuary's captured page lists no secondary skills.
- `recent-activity`: array of `{"achievement_id":1186,"name":"...","relative_time":"15 hours ago"}`. These are relative source strings, not exact timestamps and not evidence of last login.
- `pvp-summary`: object of displayed kill counters, such as `{"Total Kills":16,"Kills Today":0}`.

`equipment-details` returns 19 slots, retaining empty positions. Example from the saved Sengtuary profile:

```json
{
  "slot": "head",
  "item_id": 51162,
  "enchant_code": 3817,
  "gem_codes": [3628, 3518, 0],
  "quality": 4,
  "icon_url": "http://cdn.warmane.com/wotlk/icons/large/inv_helmet_154.jpg"
}
```

Slots follow the observed WotLK armory layout: head, neck, shoulders, back, chest, shirt, tabard, wrists; hands, waist, legs, feet, two fingers, two trinkets; main hand, off hand, ranged/relic. Empty slots have `item_id: null`; unknown enchant codes are null; absent gem parameters produce `[]`. Zero entries within supplied gem parameters are preserved. Unexpected slot counts fail validation.

`enchant_code` and `gem_codes` are the numeric tooltip parameters in Warmane's HTML. The [linked tooltip script](https://cdn.cavernoftime.com/api/tooltip.js) forwards `ench` and `gems` to its item tooltip service. This does not establish that gem codes are item IDs. There is no automatic name lookup, item-level lookup, transmog reconstruction, or GearScore calculation. Join item names from the JSON `equipment` view by item ID if needed; do not join by array index because JSON omits empty slots.

## Talents and glyphs

`talent-builds` returns a list of:

```json
{
  "spec_index": 1,
  "active": true,
  "trees": [{
    "name": "Holy",
    "points": 11,
    "talents": [{"spell_id":20208,"points":5,"max_points":5,"tier":0,"column":1}]
  }],
  "glyphs": [{"kind":"major","name":"...","spell_id":123}]
}
```

The abbreviated example illustrates the shape; full results have three trees and all displayed talent nodes, including unspent nodes. `tier`, `column` and `spec_index` are zero-based. A spell link on an unspent node is not a learned spell. Per-node point totals must agree with the displayed tree totals or parsing fails.

`glyphs` returns just `spec_index`, `active` and `glyphs` for each build. The two endpoints share the talents-page cache. `active` comes from the selected spec marker; if the page has no selector it is null rather than inferred. Sengtuary has two populated specs with six glyphs each in the captured sample.

## Achievements and statistics

1. GET `achievement-categories` or `statistic-categories` to discover IDs. Each item has string `id`, `name`, and optional `parent_id`.
2. GET `achievements?category=92` or `statistics?category=<id>` to fetch that category. Only `summary` or positive numeric IDs up to six digits are accepted. Unknown categories that do not produce the expected structure return 502.
3. GET `achievement-summary` for completion counts. `achievements` without a category is an alias for this summary. `statistics` defaults to its summary category.

The wrapper makes the same read-only POST used by Warmane's UI, with `category` as form data. Each category has its own cache entry. No page scripts are executed.

Achievement summary data: `{"completed":162,"total":1058,"categories":[{"name":"General","completed":24,"total":54}, ...]}`. A category such as Feats of Strength may have `total: null`.

Achievement category data: `{"category":"92","achievements":[...]}`. Entries contain `achievement_id`, `name`, `description`, `points`, `earned`, `date_text`, `reward` and `criteria_text`. Dates stay as source strings such as `Earned 06/28/2026`; no timezone or exact completion instant is invented. Optional criteria are null when the category response does not supply them. Per-achievement criteria loading is not implemented; no verified loader was found in the inspected armory script.

Statistics data: `{"category":"summary","statistics":[{"description":"Quests completed","value":418,"display_value":"418"}]}`. A source placeholder `- -` becomes `value: null`, retaining its original `display_value`. Counters represent what the armory reports; they are not guaranteed complete or mutually consistent.

## Reputation and collections

`reputation` returns faction name, standing, displayed `progress`, `maximum` and `is_exalted_placeholder`. Some Exalted entries use 999/999; that flag distinguishes the placeholder from an actual reputation total. Progress is within the displayed standing, not a cumulative amount. A page with no recognizable reputation rows returns 502 because an authentic empty reputation layout has not been verified.

`collections` returns `{"mounts":[...],"companions":[...]}`. Entries contain the displayed name, linked `item_id`, and source URL. Item IDs refer to linked collection items, not mount spell IDs. Valid empty tab containers yield empty arrays.

## PvP match history

`match-history?offset=0&limit=100` returns `{"matches":[...],"total":N,"offset":0,"limit":100}`, newest first. Match rows include `match_id`, team, outcome, displayed rating, start-time text and source Unix timestamp, duration, and map. Local pagination does not reduce the size of Warmane's full-page response.

Use `matches/{match_id}` for participants, e.g. `/api/v1/characters/Blackrock/Cowysparttwo/matches/31806864`. Results contain character and realm, class/race/gender IDs, plain-text team, damage, healing, deaths, killing blows, and displayed personal/MMR values with changes. Class/race IDs here are not the masks in the JSON summaries. HTML formatting from the upstream response is stripped. A response without the requested character/realm is rejected.

Sengtuary's captured history is empty; Warmane emits a blank placeholder row that is explicitly recognized and omitted. Populated history and participant details were verified with Cowysparttwo on Blackrock.

## Metadata and pacing

HTML views have `meta.source: "warmane_html"`; category views use `warmane_ajax_html`, and match details use `warmane_ajax_json`. `source_url`, `fetched_at`, `cached`, and `cache_ttl_seconds` identify the source and freshness. AJAX views add `source_parameters` and category views also add `source_category`.

All sources share the same upstream request budget and bounded cache. Cached related views can be requested immediately. Different uncached pages may return 503 with `Retry-After`; the [lookup example](../examples/character_lookup.py) prints JSON and reports retry delays on stderr. Source error responses and parse failures are not cached. See [README](../README.md) for the full error contract.
