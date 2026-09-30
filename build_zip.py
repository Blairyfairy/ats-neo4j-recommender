#!/usr/bin/env python3
"""Package the repo into dist/ats-neo4j-recommender.zip (no __MACOSX / .DS_Store)."""
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "dist" / "ats-neo4j-recommender.zip"
SKIP = {".git", "dist", "__pycache__", ".terraform", ".env"}
SKIP_SUFFIX = {".pyc", ".tfstate"}
SKIP_NAME = {".DS_Store", ".terraform.lock.hcl"}


def include(p: Path) -> bool:
    if p.name in SKIP_NAME or p.suffix in SKIP_SUFFIX:
        return False
    for part in p.parts:
        if part in SKIP:
            return False
    return True


def main() -> None:
    OUT.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(ROOT.rglob("*")):
            if f.is_file() and include(f.relative_to(ROOT)):
                zf.write(f, f"ats-neo4j-recommender/{f.relative_to(ROOT).as_posix()}")
    print(f"Wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
