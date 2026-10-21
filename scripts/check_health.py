"""A scheduler-friendly readiness probe: JSON event and nonzero exit on failure."""

import argparse
import json
import urllib.error
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000/ready")
    args = parser.parse_args()
    try:
        with urllib.request.urlopen(args.url, timeout=5) as response:
            ready = response.status == 200
    except (OSError, urllib.error.URLError):
        ready = False
    print(json.dumps({"event": "readiness_ok" if ready else "readiness_failed"}))
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
