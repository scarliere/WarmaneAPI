"""Commit staged changes with a version-first subject from pyproject.toml."""
import argparse
from pathlib import Path
import re
import subprocess
import tomllib


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("type", choices=("feat", "fix", "docs", "test", "refactor", "perf", "build", "ci", "chore", "revert"))
    parser.add_argument("description", help="Short description without a version prefix")
    parser.add_argument("--body", help="Optional commit body")
    parser.add_argument("--dry-run", action="store_true", help="Print the subject without changing Git")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    if not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version):
        parser.error("Expected a stable MAJOR.MINOR.PATCH version in pyproject.toml")
    description = args.description.strip()
    if not description or any(c in description for c in "\r\n\x00"):
        parser.error("Description must be a nonempty single line")
    subject = f"v{version}: {args.type}: {description}"
    print(subject, flush=True)
    if args.dry_run:
        return 0
    command = ["git", "commit", "-m", subject]
    if args.body:
        command.extend(["-m", args.body])
    try:
        return subprocess.run(command, cwd=root, check=False).returncode
    except FileNotFoundError:
        parser.exit(1, "Git is not installed or is not on PATH.\n")


if __name__ == "__main__":
    raise SystemExit(main())
