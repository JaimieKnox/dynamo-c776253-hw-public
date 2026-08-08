#!/usr/bin/env python3
"""Trusted sample smoke. Runs against /app/norctl and /app/cases only."""

from __future__ import annotations

import json
import sys
from pathlib import Path

EXPECT = {
    "sample_01": {
        "nvs": {"channel": "6", "ssid": "labnet"},
        "boot_bank": "X",
        "sec_rev": 2,
        "sec_floor": 1,
    },
    "sample_02": {
        "nvs": {"mode": "run"},
        "boot_bank": "Y",
        "sec_rev": 3,
        "sec_floor": 1,
    },
}


def main() -> int:
    app = Path("/app")
    cases = app / "cases"
    sys.path.insert(0, str(app))
    from norctl.runtime import run_case  # noqa: WPS433

    for cid, exp in sorted(EXPECT.items()):
        script = json.loads((cases / cid / "script.json").read_text(encoding="utf-8"))
        got = run_case(script)
        for key in (
            "case_id",
            "nvs",
            "boot_bank",
            "sec_rev",
            "tip_seq",
            "sec_floor",
        ):
            if key not in got:
                print(f"FAIL {cid}: missing {key}", file=sys.stderr)
                return 1
        if got["case_id"] != cid:
            print(f"FAIL {cid}: case_id", file=sys.stderr)
            return 1
        if got["nvs"] != exp["nvs"]:
            print(f"FAIL {cid}: nvs {got['nvs']!r} != {exp['nvs']!r}", file=sys.stderr)
            return 1
        if got["boot_bank"] != exp["boot_bank"]:
            print(f"FAIL {cid}: boot_bank", file=sys.stderr)
            return 1
        if got["sec_rev"] != exp["sec_rev"]:
            print(f"FAIL {cid}: sec_rev", file=sys.stderr)
            return 1
        if got["sec_floor"] != exp["sec_floor"]:
            print(f"FAIL {cid}: sec_floor", file=sys.stderr)
            return 1
        if not isinstance(got["tip_seq"], int):
            print(f"FAIL {cid}: tip_seq type", file=sys.stderr)
            return 1
        print(f"OK {cid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
