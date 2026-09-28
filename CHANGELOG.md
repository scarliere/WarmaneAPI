# Changelog

Versions use Semantic Versioning (`MAJOR.MINOR.PATCH`). Before 1.0.0, minor releases may change the API contract; patch releases contain compatible fixes. From 1.0.0 onward, incompatible API changes require a major version, compatible features a minor version, and compatible fixes a patch version. Release tags use the `v` prefix, for example `v0.4.0`. The response schema version is separate from the application version.

## 0.4.0 — 2026-09-28

### Added

- Character lookup by name with an optional realm, defaulting to Icecrown.
- Grouped character JSON including status, stats, equipment, talents, professions, collections, achievements, statistics, reputation, and PvP data.
- Lightweight online-status lookup, source freshness metadata, and explicit partial-result errors.
- Windows, macOS, and Linux setup instructions; GitHub Actions tests for Python 3.11 and 3.12 on all three platforms.
- Portable ZIP and tar.gz packaging and guild restoration archive.

### Changed

- Scoped the active API to characters; removed guild routes and their active parsers/fixtures. The previous implementation is preserved under `archive/guild-api`.
- Retained explicit-realm character URLs and the hidden, deprecated `/full` compatibility route.
- Organized historical documentation under `docs/archive`.

### Validation

- 75 offline tests passed on Linux with Python 3.12.
- Live Ahger/Icecrown lookup returned complete data and all six stat groups.
- Windows and macOS verification remains pending the GitHub Actions runs.
