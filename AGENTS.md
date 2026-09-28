# Repository instructions

## Commit messages

Every commit subject must start with the current project version from `pyproject.toml`, with a lowercase `v` prefix:

```text
v<MAJOR>.<MINOR>.<PATCH>: <type>: <description>
```

Example: `v0.4.1: fix: handle missing character stats`.

Use the repository command to generate the subject automatically:

```bash
python scripts/commit.py fix "handle missing character stats"
```

Use `python3` or the virtual environment's Python if required by the platform. Stage the intended files first; the command commits only staged changes. It does not stage, bump versions, create tags, or push. Use `--dry-run` to preview the subject.

Use Semantic Versioning according to `CHANGELOG.md`. Change the version deliberately when preparing a new version, not automatically for every commit. After a version has been tagged, assign the next intended version before committing follow-up changes; do not move existing version tags to include new work. Keep `pyproject.toml` and the FastAPI app version synchronized. Put the version first in tag annotations and release titles as well.

## Validation and scope

Run relevant checks before committing code changes. The offline suite is `python -m pytest -q`. Windows/macOS support must not be called verified unless the corresponding CI jobs passed.

The active API is character-only and defaults to Icecrown. The saved guild implementation under `archive/guild-api` is historical reference, not active application code.
