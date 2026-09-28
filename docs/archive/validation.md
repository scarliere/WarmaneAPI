# Validation

Automated tests are offline: `python -m pytest`. They use HTTPX mock transports, saved public armory responses in `tests/fixtures/live`, and synthetic cases for missing fields and markup changes.

On September 23, 2026, the portable source archive was extracted into a separate directory, its pinned dependencies installed into a fresh Python 3.12 environment, and all **64 tests passed** there. This verifies that the tests and source do not depend on the original virtual environment or the archived exploratory captures. Docker execution was not verified because this machine denied access to its Docker socket.

The fixtures cover Sengtuary/Icecrown (Paladin, two specs, empty off-hand/tabard, no listed secondary skills, empty match history), Cowysparttwo/Blackrock (populated history and participant details), Dojun/Icecrown (Druid, one spec, secondary professions), and Malaysian Raiders' ranks and boss fights. Capture manifests record source URLs and dates. Assertions describe those saved observations, not permanent live values.

The suite checks the primary response contract, status freshness metadata, named equipment matching by item ID, unknown status, JSON normalization, source caching, global pacing, partial failures, deadlines, category expansion, rank joins and pagination. Live requests are separate, manual checks and are not required to move or test the repository.

Exploratory captures and probe scripts were archived outside the source tree during cleanup. Required fixtures were retained in the test directory. The manual `scripts/capture_fixtures.py` utility can update selected live fixtures; it overwrites samples and makes paced network requests, so use it deliberately.

Limits: samples cover WotLK on Icecrown and Blackrock, not every expansion or empty-state layout. Two dependencies currently emit deprecation warnings from the test client; these do not affect the running API.
