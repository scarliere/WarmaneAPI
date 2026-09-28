# Publishing the source to GitHub

Run the offline checks before publishing:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Publish the source folders, README, dependency files, Dockerfile, and dotfiles `.gitignore`, `.gitattributes`, `.dockerignore`, `.env.example`, and `.github/workflows/tests.yml`. Keep `.venv`, `.env`, caches, `dist`, and local agent metadata out of Git; `.gitignore` covers these.

The configured remote is `https://github.com/scarliere/WarmaneAPI.git`. Use a normal clone to preserve Git history. To create an independent source-only checkout elsewhere, run `python scripts/package_repo.py`, extract the source archive, then run:

```bash
git init
git add .
git diff --cached --stat
git commit -m "Initial character API"
```

Create an empty repository in GitHub, then follow its instructions to add the remote and push. Choose a license before offering reuse permissions; this project does not currently include a license. No repository has been created or pushed automatically.

The files under `tests/fixtures/live` are saved public armory responses used for offline regression tests; the directory name does not mean tests contact Warmane. Historical development notes live under `docs/archive` and are not current API documentation.

## Releases

A GitHub Release attaches release notes and downloadable assets to a Git tag, such as `v0.4.0`. The tag identifies a particular commit. GitHub automatically offers ZIP and tar.gz downloads of that tagged source. You can additionally upload our curated source packages as release assets. A release does not run the API, install it on users' devices, or publish it to PyPI.

Recommended process:

1. Update the package version in `pyproject.toml` and the application version in `warmane_api/main.py`, plus versioned examples in documentation. The packaging script reads the package version automatically.
2. Push the changes and wait for all six jobs in **Cross-platform tests** to pass for the exact commit you intend to release. CI uses offline fixtures, not live Warmane requests. GitHub does not automatically prevent publishing a release when tests fail.
3. Run `python scripts/package_repo.py` from that checkout. It builds ZIP and tar.gz files in `dist/`, including the saved guild implementation.
4. On GitHub, open **Releases → Draft a new release**, create/select tag `v0.4.0` targeting the tested commit, and write notes describing features, breaking changes, and known limitations. For this release, mention the default Icecrown lookup and removed active guild routes.
5. Attach the two `dist/` packages. Review the draft, then publish. Use a prerelease label for experimental versions. Consumers download a package, create a local virtual environment, install dependencies, and start Uvicorn using the platform setup guide.

There is no automatic release publishing workflow in this repository; CI only tests and checks packaging. No GitHub release has been created by this setup.

Official references: [About releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases) and [Managing releases](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository).
