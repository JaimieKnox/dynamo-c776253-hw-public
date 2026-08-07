"""CLI: python3 -m norctl <cases_dir> <out_dir>"""

from __future__ import annotations

import sys
from pathlib import Path

from .runtime import run_cases_dir


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2:
        print("usage: python3 -m norctl <cases_dir> <out_dir>", file=sys.stderr)
        sys.exit(2)
    run_cases_dir(Path(argv[0]), Path(argv[1]))


if __name__ == "__main__":
    main()
