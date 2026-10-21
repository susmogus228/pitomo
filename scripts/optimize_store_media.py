"""Encode existing approved illustrations without changing their artwork."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "frontend/public/media"
ILLUSTRATIONS = {
    "hero-cat": (640, 1280, 1600),
    "pets-grid": (1792,),
    "cat-register": (640, 1280, 1600),
    "cat-login": (640, 1280, 1600),
}


def main() -> None:
    report = []
    for name, widths in ILLUSTRATIONS.items():
        source = MEDIA / f"{name}.png"
        with Image.open(source) as original:
            for width in widths:
                actual = min(width, original.width)
                height = round(original.height * actual / original.width)
                target = MEDIA / f"{name}-{width}.webp"
                picture = original.convert("RGBA").resize((actual, height), Image.Resampling.LANCZOS)
                picture.save(target, "WEBP", quality=88, method=6)
                with Image.open(target) as checked:
                    assert checked.size == (actual, height)
                    assert checked.format == "WEBP"
                    checked.verify()
                report.append({"source": source.name, "file": target.name, "width": actual,
                               "height": height, "source_bytes": source.stat().st_size,
                               "bytes": target.stat().st_size})
    versions = {"/media/" + path.relative_to(MEDIA).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()[:12]
                for path in sorted(MEDIA.rglob("*")) if path.is_file()}
    (ROOT / "frontend/src/mediaVersions.json").write_text(json.dumps(versions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    destination = ROOT / "verification/audit-media-optimization.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
