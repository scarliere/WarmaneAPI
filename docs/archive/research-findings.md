# Research background

The implementation began with the [Warmane API feedback discussion](https://forum.warmane.com/showthread.php?t=463405) and its [linked tutorial](https://forum.warmane.com/showthread.php?t=383159). These are community reports, not an official API specification.

Two investigative passes found that the JSON API supplies character/guild summaries, while public HTML exposes combat stats, enchant/gem tooltip codes, secondary skills, detailed talent ranks, glyphs, recent achievements, guild rank labels, collections and reputation. Public UI POST loaders supply achievement/statistic categories and PvP match participants. Guild HTML includes recorded boss fights.

Guessed JSON suffixes can return the same summary, including an invented suffix. HTTP 200 alone is not proof of a separate capability. The character achievements API GET returned an empty body in the sampled request; the HTML page's read-only category POST returned usable data.

Known inconsistencies include numeric strings/nulls, nested guild professions, empty transmog fields, guild faction differences between HTML and JSON, relative achievement ages and Exalted reputation displayed as 999/999. Parsers preserve or explicitly label these values rather than inventing missing information.

Current routes are documented in [the API contract](../api.md) and [extended endpoints](../extended-api.md). Saved source fixtures required by tests are in `tests/fixtures/live`; exploratory snapshots and scripts were archived outside the distributable repository during cleanup.
