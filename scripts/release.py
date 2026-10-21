"""Replace an existing Compose API and restore its exact image on failed readiness.

Run migrations and validate backward schema compatibility before invoking this
script. Database migrations are deliberately never reversed automatically.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def command(args, env):
    return subprocess.run(args, env=env, cwd=ROOT, text=True, capture_output=True, check=False)


def deploy(image: str, timeout: int = 90) -> int:
    env = os.environ.copy()
    previous = command(["docker", "compose", "ps", "--quiet", "api"], env)
    container = previous.stdout.strip()
    if previous.returncode or not container or "\n" in container:
        raise ValueError("Expected exactly one existing API container; use compose for initial start")
    inspected = command(["docker", "inspect", "--format", "{{.Image}}", container], env)
    if inspected.returncode or not inspected.stdout.strip().startswith("sha256:"):
        raise ValueError("Cannot determine the existing immutable image ID")
    previous_image = inspected.stdout.strip()
    env["PETSHOP_IMAGE"] = image
    args = ["docker", "compose", "up", "--detach", "--no-deps", "--no-build",
            "--wait", "--wait-timeout", str(timeout), "api"]
    candidate = command(args, env)
    if candidate.returncode == 0:
        print(json.dumps({"event": "release_succeeded", "image": image}))
        return 0
    env["PETSHOP_IMAGE"] = previous_image
    rollback = command(args, env)
    print(json.dumps({"event": "release_failed", "rollback_succeeded": rollback.returncode == 0,
                      "previous_image": previous_image,
                      "manual_action": (
                          "Set PETSHOP_IMAGE in .env to previous_image before any subsequent "
                          "docker compose up; the saved configuration was not changed."
                          if rollback.returncode == 0
                          else "Restore API readiness manually; rollback did not become healthy."
                      )}), file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="Prebuilt immutable image tag/digest")
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error("--timeout must be positive")
    try:
        return deploy(args.image, args.timeout)
    except (OSError, ValueError):
        print(json.dumps({"event": "release_preflight_failed"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
