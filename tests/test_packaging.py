import importlib.util
from pathlib import Path
import tarfile
import zipfile

import pytest

spec = importlib.util.spec_from_file_location(
    "package_repo", Path(__file__).resolve().parents[1] / "scripts/package_repo.py")
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)


@pytest.mark.parametrize("suffix", ["zip", "tar.gz"])
def test_portable_archive_preserves_source_and_excludes_local_files(tmp_path, suffix):
    root = tmp_path / "source with spaces"
    included = ["warmane_api/main.py", ".env.example", ".github/workflows/tests.yml",
                "archive/guild-api/snapshot.tar.gz"]
    excluded = [".env", ".env.local", ".venv/config", ".git/config", ".codex/state",
                "__pycache__/app.pyc", "local.egg-info/PKG-INFO", "dist/old.zip"]
    for name in included + excluded:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")
    output = root / f"release.{suffix}"
    packager.package(root, output)
    if suffix == "zip":
        with zipfile.ZipFile(output) as archive:
            names = archive.namelist()
            assert archive.read("WarmaneAPI/warmane_api/main.py") == b"fixture"
    else:
        with tarfile.open(output) as archive:
            names = archive.getnames()
            assert archive.extractfile("WarmaneAPI/warmane_api/main.py").read() == b"fixture"
    assert set(names) == {"WarmaneAPI/" + name for name in included}
    assert all("\\" not in name for name in names)
