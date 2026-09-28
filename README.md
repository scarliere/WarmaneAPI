# Warmane Character API

A read-only REST API for looking up a Warmane **character by name and realm**, with a complete overview and a lightweight online-status check. It reads the public armory; no Warmane account credentials are needed.

## Quick start

Python 3.11+ is required; Python 3.12 is the tested version. Run from the project directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
uvicorn warmane_api.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Windows PowerShell commands that do not require activation are in the [platform setup guide](docs/migration.md). On Debian/Ubuntu, creating the environment may require the `python3-venv` package. Use `requirements.txt` instead of `requirements-dev.txt` for runtime dependencies only.

Open **http://127.0.0.1:8000/docs**. The root URL also opens the documentation. OpenAPI is at `/openapi.json` and liveness is at `/health`.

## Primary endpoints

| Method and path | Purpose |
| --- | --- |
| `GET /api/v1/characters/{name}?realm=Icecrown` | Combined character data, including the stat breakdown |
| `GET /api/v1/characters/{name}/status?realm=Icecrown` | Lightweight online-status polling with observation time |
| `GET /api/v1/characters/{realm}/{name}/summary` | Underlying JSON summary; `raw=true` preserves upstream fields/types |

Omitting `realm` defaults to **Icecrown**. For another realm, use `?realm=Blackrock`. Empty or malformed realm values return 422. Existing explicit realm paths remain supported.

Example: [Ahger on Icecrown](http://127.0.0.1:8000/api/v1/characters/Ahger).

```bash
curl --max-time 130 'http://127.0.0.1:8000/api/v1/characters/Ahger'
curl 'http://127.0.0.1:8000/api/v1/characters/Ahger/status'
```

The primary response groups data under:

```text
data.character       Identity, class, level, guild, achievement points
data.status          online, observed_at, cached, cache_ttl_seconds
data.stats           Attributes, Melee, Ranged, Defense, Spell, Resistances
data.equipment       Named items by slot, quality, enchant/gem codes
data.professions     primary and secondary skills
data.talent_builds   Detailed builds separated by spec
data.glyphs          Glyphs separated by spec
data.collections     Mounts and companions
data.reputation      Faction standings
data.achievements    Summary, categories, optional category data, recent activity
data.statistics      Summary, categories, optional category data
data.pvp             Summary, teams, full match history, optional match details
meta                 schema_version, completeness, sources, errors, omissions
```

`meta.schema_version` is `1.0`. The typed response schema is available in OpenAPI. See [the response contract](docs/api.md) for field details and partial results.

A cold overview usually takes **40–60 seconds** because its ten upstream sources are paced. Related fields share source pages; cached calls are faster. For regular online/offline checks, poll `/status`, not the full overview. `online: null` means unknown; an upstream failure is an error, not an offline status. `observed_at` is our retrieval time, not the character's last login.

## Optional deeper data

The primary route accepts:

| Parameter | Default | Range/purpose |
| --- | --- | --- |
| `include_categories` | `false` | Fetch each listed achievement/statistics category |
| `match_details_limit` | `0` | Fetch participant details for 0–100 unique matches |
| `match_details_offset` | `0` | Start at this offset in newest-first unique matches |
| `max_wait_seconds` | `120` | Overall lookup budget, 1–900 seconds |

Expansions can take several minutes. Full match history is included by default; participant detail expansion is opt-in. `meta.omitted` states the unrequested scope. Configure any reverse-proxy timeout above the lookup budget.

## Configuration and limits

Export environment variables before starting the server. [.env.example](.env.example) lists the supported settings; `.env` is **not automatically loaded**.

| Variable | Default |
| --- | --- |
| `WARMANE_CACHE_TTL_SECONDS` | `60` seconds for JSON/status |
| `WARMANE_HTML_CACHE_TTL_SECONDS` | `300` seconds for HTML/AJAX |
| `WARMANE_MIN_INTERVAL_SECONDS` | `4` seconds between upstream requests |
| `WARMANE_TIMEOUT_SECONDS` | `15` seconds per network operation |
| `CORS_ORIGINS` | Empty; comma-separated browser origins if needed |

The shared in-memory cache holds 256 source entries. One upstream request and one combined lookup can run at a time. Use **one worker/instance**; multiple processes do not share the limiter. The four-second interval is our policy, not a verified Warmane quota. Cached requests do not spend the upstream budget.

Standalone requests can return 503 while the budget is busy. Honor `Retry-After`; the combined lookup waits for routine pacing internally. Upstream 429 honors its retry header or uses a 60-second fallback. Unknown JSON API errors trigger a minimum 60-second cooldown without guessing the error code's meaning.

The service has no authentication or per-client admission limit. If making it publicly accessible, configure access control and request limits in your gateway. CORS is browser access configuration, not authentication.

## Development and migration

```bash
python -m pytest
python examples/character_lookup.py --name Ahger --realm Icecrown
python scripts/package_repo.py
```

The example prints the primary response as JSON; add `--status` for a lightweight check. Packaging creates `dist/WarmaneAPI-0.4.1.zip` and `dist/WarmaneAPI-0.4.1.tar.gz`, excluding `.venv`, caches, secrets, editor/agent metadata and generated artifacts. Test fixtures and pinned dependency files are included. **Recreate the environment on the dev device; do not copy `.venv`.** See [migration instructions](docs/migration.md).

An optional [Dockerfile](Dockerfile) uses Python 3.12 and a non-root user. Keep one worker. Dependencies are pinned in `requirements.txt` and `requirements-dev.txt`; `pyproject.toml` records supported version ranges for package installations.

## Scope and compatibility

This service reads public data for a specific character and realm. It has no guild lookup endpoints, account access, in-game addon, or location tracking. A character's guild name remains part of its identity.

Individual [character sections](docs/extended-api.md) remain available with explicit realm paths. The previous `/api/v1/characters/{realm}/{name}` overview and `/status` URLs still work. The deprecated `/full` route is retained for existing clients but excluded from OpenAPI; new clients should use the primary route.

Version 0.4 removes the guild routes. Version 0.3 changed the base character URL from an upstream summary to a grouped overview; summary clients should use `/{realm}/{name}/summary`.

## Data quality and tests

Automated tests run offline using saved public responses and synthetic edge cases. Coverage includes Sengtuary/Icecrown, Cowysparttwo/Blackrock and Dojun/Icecrown. Historical validation and research are in [docs/archive](docs/archive/README.md); they are not the current API contract.

HTML layout changes can cause parse errors. Successful sections are retained with `meta.complete: false` and named errors; null sections are not silently replaced with empty data. GearScore, authoritative last-online time, current location, guild notes/MOTD, raid-lockout expiration and reliable transmog mappings are not supplied. Enchant/gem codes remain the observed tooltip codes, not guessed item IDs or names.

For GitHub preparation, see [publishing instructions](docs/publishing.md).

The previous guild endpoints, tests, and fixtures are preserved in the [guild restoration archive](archive/guild-api/README.md) for future development.

Cross-platform CI tests Python 3.11/3.12 on Windows, macOS, and Linux after push. Only Linux has been verified locally; check the GitHub Actions results before publishing a release. See [releases](docs/publishing.md#releases).

Version history and the Semantic Versioning policy are in [CHANGELOG.md](CHANGELOG.md).

For version-first commits on any dev PC, stage your changes and run `python scripts/commit.py <type> "description"`. The command reads the version from `pyproject.toml`; [AGENTS.md](AGENTS.md) records the convention for coding agents.
