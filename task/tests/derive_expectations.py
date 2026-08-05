#!/usr/bin/env python3
"""Phase A: seal trusted-job expectations, then remove the reference model."""

from __future__ import annotations

import json
import os
from pathlib import Path

from ref_model import expected_for_jobs

TRUSTED_SCRIPTS = Path(__file__).resolve().parent / "trusted_job_scripts"
SEAL_PATH = Path("/logs/verifier/expected.json")
REF_MODEL = Path(__file__).resolve().parent / "ref_model.py"


def main() -> int:
    SEAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    golden = expected_for_jobs(TRUSTED_SCRIPTS)
    payload = {"jobs": golden}
    SEAL_PATH.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    # Remove the reference engine so graded pytest cannot import it.
    if REF_MODEL.is_file():
        os.remove(REF_MODEL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
