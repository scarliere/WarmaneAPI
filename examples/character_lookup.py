"""Print a character overview or lightweight status as JSON."""
import argparse
import json
import sys
from urllib.parse import quote

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--name", required=True)
    parser.add_argument("--realm", default="Icecrown")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    path = f"/api/v1/characters/{quote(args.name, safe='')}"
    if args.status:
        path += "/status"
    try:
        response = httpx.get(args.base_url.rstrip("/") + path, params={"realm": args.realm}, timeout=130)
        payload = response.json()
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        if response.is_error:
            if "Retry-After" in response.headers:
                print(f"Retry after {response.headers['Retry-After']} seconds", file=sys.stderr)
            return 1
        return 2 if payload.get("meta", {}).get("complete") is False else 0
    except (httpx.RequestError, ValueError) as exc:
        print(f"Lookup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
