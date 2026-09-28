"""Create portable ZIP/tar.gz source archives without local environments or secrets."""
import argparse
from pathlib import Path
import tarfile
import tomllib
import zipfile


EXCLUDED = {".git", ".agents", ".codex", ".venv", "venv", "__pycache__",
            ".pytest_cache", "dist", "build", "htmlcov"}


def source_files(root, output):
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_symlink() or not path.is_file() or path.resolve() == output.resolve():
            continue
        if any(p in EXCLUDED or p.endswith(".egg-info") for p in relative.parts):
            continue
        if path.name.startswith(".env") and path.name != ".env.example":
            continue
        if path.suffix in {".pyc", ".log"} or path.name in {".coverage", ".DS_Store", "Thumbs.db"}:
            continue
        yield path, "WarmaneAPI/" + relative.as_posix()


def package(root, output):
    if not (output.name.endswith(".tar.gz") or output.suffix == ".zip"):
        raise ValueError("Output must end in .zip or .tar.gz")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix == ".zip":
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path, name in source_files(root, output):
                archive.write(path, arcname=name)
    else:
        with tarfile.open(output, "w:gz") as archive:
            for path, name in source_files(root, output):
                archive.add(path, arcname=name, recursive=False)


def main():
    root = Path(__file__).resolve().parents[1]
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional .zip or .tar.gz path; defaults to both in dist/.")
    args = parser.parse_args()
    outputs = [args.output.resolve()] if args.output else [
        root / f"dist/WarmaneAPI-{version}.{suffix}" for suffix in ("zip", "tar.gz")]
    for output in outputs:
        package(root, output)
        print(output)


if __name__ == "__main__":
    main()
