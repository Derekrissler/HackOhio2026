"""Regenerate data/seed/ deterministically: `python -m seedgen [--out DIR]`."""

import argparse
import shutil
from pathlib import Path

from app.db import REPO_ROOT
from seedgen.build import build

DEFAULT_OUT = REPO_ROOT / "data" / "seed"


def write(out_dir: Path) -> int:
    for sub in ("canvas_json", "manual", "files"):
        shutil.rmtree(out_dir / sub, ignore_errors=True)
    files = build()
    for rel, data in files.items():
        path = out_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return len(files)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    n = write(args.out)
    print(f"Wrote {n} files to {args.out}")


if __name__ == "__main__":
    main()
