# Moving to the dev device

## Package and transfer

Run `python scripts/package_repo.py` from any directory. Transfer either `dist/WarmaneAPI-0.4.1.zip` (convenient on Windows) or `dist/WarmaneAPI-0.4.1.tar.gz` to the dev device and extract it. The archive includes application code, documentation, dependency pins, examples and offline test fixtures. It excludes `.venv`, caches, `.git`, agent/editor metadata, `.env` files and generated artifacts. `.env.example` is included.

Keep credentials and local environment configuration separate. No Warmane credentials are needed. Recreate the Python environment on the destination; copying an existing virtual environment across devices is unreliable.

## Install and run

Linux/macOS, from the extracted `WarmaneAPI` directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest
.venv/bin/python -m uvicorn warmane_api.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
.venv\Scripts\python -m uvicorn warmane_api.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Use Python 3.12 for the recommended setup. Linux/Python 3.12 has been tested locally. GitHub Actions is configured to test Python 3.11 and 3.12 on Windows, macOS, and Linux; those results must pass before claiming verification on those platforms. Other Python versions are not in the test matrix. Installing pinned dependencies requires PyPI access (or a separately prepared wheel cache). Start from the project root so `warmane_api` is importable; alternatively install the project with `python -m pip install --no-deps -e .` after dependencies.

These commands call the virtual environment directly; PowerShell script activation and changes to execution policy are unnecessary. Install Python 3.12 first (the Windows command assumes the Python launcher is installed); use `python -m venv .venv` if `py` is unavailable. On macOS/Linux, ensure `python3 --version` identifies the intended version. Debian/Ubuntu may require the matching `python3-venv` package.

The native service does not require Docker or operating-system-specific packages. Dependencies are installed for the destination architecture, including Pydantic's native component; never transfer an existing `.venv`. GitHub's matrix covers the architectures of its selected hosted runners, not every OS/CPU combination.

Set overrides before starting:

```bash
# macOS / Linux
export WARMANE_CACHE_TTL_SECONDS=60
```

```powershell
# Windows PowerShell
$env:WARMANE_CACHE_TTL_SECONDS = "60"
```

Use the browser at `/docs` or `python examples/character_lookup.py --name Ahger` with your virtual environment's Python on any OS. In Windows PowerShell, use `curl.exe` if following curl examples, to avoid the Windows PowerShell `curl` alias.

Export any overrides from `.env.example` before starting. The server does not load `.env` automatically. The status/HTML cache lives in memory and starts empty after migration. No database or runtime state needs copying.

## Verify

Open `http://127.0.0.1:8000/health`, then `/docs`. Try the lightweight `/api/v1/characters/Ahger/status` first. The primary `/api/v1/characters/Ahger` route may need 40–60 seconds on a cold cache; set client/proxy timeouts above the configured lookup budget.

Omitting the realm uses `Icecrown`; override it with `?realm=Blackrock`. Unknown upstream resources can return an unexpected HTML page rather than a useful 404. For failed calls inspect the JSON error code, and for partial overviews inspect `meta.errors`.

## Optional container

```bash
docker build -t warmane-api:0.4.1 .
docker run --rm -p 127.0.0.1:8000:8000 --env-file .env.example warmane-api:0.4.1
```

The container runs as a non-root user and exposes a health check. Its single worker preserves the in-process request budget. Do not scale replicas/workers without a shared cache and limiter. Docker requires network access to fetch the base image and packages; availability of Docker on the target device must be checked there.

The native Python migration path was verified from the extracted archive in a fresh environment. The optional container could not be tested on the source machine because Docker socket access was denied.

## Repository layout

```text
warmane_api/          App, source client, parsers, aggregation, public models
tests/               Offline regressions and required fixtures
docs/                API contract, migration, secondary routes and provenance
examples/            JSON lookup command-line example
scripts/             Portable packaging and manual fixture capture
requirements*.txt    Tested dependency pins
pyproject.toml       Python package metadata and supported dependency ranges
Dockerfile           Optional container runtime
.env.example         Supported runtime settings
```

The migration archive is a source snapshot, not a Git-history backup. Clone the GitHub repository when you need commit history and remotes on the dev device.
