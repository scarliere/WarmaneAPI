# Guild API restoration archive

Preserved from version 0.3.0 before the character-only cleanup. This complete source snapshot includes the guild routes, parsers, client, offline tests, public HTML fixtures, documentation, and dependency pins. It is stored in the repository so it survives migration and GitHub publication; it is not imported by the active application.

## Saved endpoints

All use GET:

- `/api/v1/guilds/{realm}/{name}` — summary; optional `raw=true`.
- `/api/v1/guilds/{realm}/{name}/members` — roster with online/class/min-level filters, pagination, and optional ranks.
- `/api/v1/guilds/{realm}/{name}/ranks` — public roster rank labels.
- `/api/v1/guilds/{realm}/{name}/boss-fights` — recorded encounters, newest first, with pagination.

These routes required an explicit realm. Boss-fight history does not indicate current instance presence or active raid lockouts.

## Restore later

1. Verify the archive against `SHA256SUMS` and extract it into a separate directory, outside the active source tree.
2. Review `warmane_api/main.py` for the four route handlers, `warmane_api/parsers.py` for `guild_ranks`, `boss_fights`, and guild identity validation in `parse_page`, and `warmane_api/client.py` for the `guild-summary` page mapping.
3. Port those pieces into the current version. Do not overwrite the current files wholesale: the archived application predates default-Icecrown character routes.
4. Restore guild cases from `tests/test_api.py` and `tests/test_html.py`, plus `tests/fixtures/live/guild-summary.html` and `guild-boss-fights.html`. Documentation is in the snapshot's `docs/extended-api.md`; fixture capture support is in `scripts/capture_fixtures.py`.
5. Run the offline tests and revalidate the public Warmane pages before enabling routes; upstream layouts may have changed.

The archive contains public test data, not Warmane account credentials. The active API remains character-only. The normal source packaging script includes this archive.
