#!/usr/bin/env python3
"""Run sample_* jobs and check schema plus expected kv/boot agreement."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# Sample packs stay green under the shipped firmware and under the repaired tree.
EXPECT = {
    "sample_01": {
        "kv": {"channel": "6", "ssid": "labnet"},
        "boot_slot": "A",
        "security_version": 2,
        "anti_rollback_min": 1,
    },
    "sample_02": {
        "kv": {"mode": "run"},
        "boot_slot": "B",
        "security_version": 3,
        "anti_rollback_min": 1,
    },
}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    jobs = root / "jobs"
    sys.path.insert(0, str(root))
    from fw.device import run_job  # noqa: WPS433

    for jid, exp in sorted(EXPECT.items()):
        script = json.loads((jobs / jid / "script.json").read_text(encoding="utf-8"))
        got = run_job(script)
        for key in (
            "job_id",
            "kv",
            "boot_slot",
            "security_version",
            "generation",
            "anti_rollback_min",
        ):
            if key not in got:
                print(f"FAIL {jid}: missing {key}", file=sys.stderr)
                return 1
        if got["job_id"] != jid:
            print(f"FAIL {jid}: job_id", file=sys.stderr)
            return 1
        if got["kv"] != exp["kv"]:
            print(f"FAIL {jid}: kv {got['kv']!r} != {exp['kv']!r}", file=sys.stderr)
            return 1
        if got["boot_slot"] != exp["boot_slot"]:
            print(f"FAIL {jid}: boot_slot", file=sys.stderr)
            return 1
        if got["security_version"] != exp["security_version"]:
            print(f"FAIL {jid}: security_version", file=sys.stderr)
            return 1
        if got["anti_rollback_min"] != exp["anti_rollback_min"]:
            print(f"FAIL {jid}: anti_rollback_min", file=sys.stderr)
            return 1
        if not isinstance(got["generation"], int):
            print(f"FAIL {jid}: generation type", file=sys.stderr)
            return 1
        print(f"OK {jid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
