"""Capture a small fixed set of public pages, five seconds apart. Run manually."""
import json
import argparse
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1] / "tests/fixtures/live"
REQUESTS = [
    ("sengtuary-summary", "api/character/Sengtuary/Icecrown/summary", None),
    *[(f"sengtuary-{section}", f"character/Sengtuary/Icecrown/{section}", None)
      for section in ("profile", "talents", "achievements", "statistics", "mounts-and-companions", "reputation", "match-history")],
    ("sengtuary-achievement-summary", "character/Sengtuary/Icecrown/achievements", "summary"),
    ("sengtuary-achievement-general", "character/Sengtuary/Icecrown/achievements", "92"),
    ("sengtuary-statistics-summary", "character/Sengtuary/Icecrown/statistics", "summary"),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--additional", action="store_true")
    args = parser.parse_args()
    requests = REQUESTS
    if args.additional:
        requests = [
            *[(f"blackrock-{section}", f"character/Cowysparttwo/Blackrock/{section}", None)
              for section in ("profile", "talents", "match-history")],
        ]
    ROOT.mkdir(parents=True, exist_ok=True)
    manifest_path = ROOT / ("manifest-additional.json" if args.additional else "manifest.json")
    manifest = []
    with httpx.Client(base_url="https://armory.warmane.com/", timeout=25) as client:
        for index, (name, path, category) in enumerate(requests):
            if index:
                time.sleep(5)
            if category is None:
                response = client.get(path)
            else:
                response = client.post(path, data={"category": category}, headers={"X-Requested-With": "XMLHttpRequest"})
            response.raise_for_status()
            is_json = category is not None or path.startswith("api/")
            if is_json and "error" in response.json():
                raise RuntimeError("Upstream API error; stopping without retry")
            filename = name + (".json" if is_json else ".html")
            (ROOT / filename).write_bytes(response.content)
            manifest.append({"file": filename, "url": str(response.url), "method": response.request.method,
                             "category": category, "fetched_at": datetime.now(timezone.utc).isoformat()})
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            print(filename, response.status_code, len(response.content), flush=True)


if __name__ == "__main__":
    main()
