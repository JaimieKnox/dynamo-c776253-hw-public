"""CLI: python3 -m fw <jobs_dir> <output_dir>"""

from __future__ import annotations

import sys
from pathlib import Path

from .device import run_jobs_dir


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2:
        print("usage: python3 -m fw <jobs_dir> <output_dir>", file=sys.stderr)
        sys.exit(2)
    run_jobs_dir(Path(argv[0]), Path(argv[1]))


if __name__ == "__main__":
    main()
