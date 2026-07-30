"""Verifier tests mapped 1:1 to instruction.md success criteria."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from ref_model import expected_for_jobs

OUT = Path("/app/output")
JOBS = Path("/app/jobs")
REQUIRED = {
    "job_id",
    "kv",
    "boot_slot",
    "security_version",
    "generation",
    "anti_rollback_min",
}


def _job_ids():
    return sorted(p.name for p in JOBS.iterdir() if (p / "script.json").is_file())


def _load_report():
    path = OUT / "batch_report.jsonl"
    assert path.is_file(), "missing batch_report.jsonl"
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def _load_recovered(job_id: str):
    path = OUT / job_id / "recovered.json"
    assert path.is_file(), f"missing recovered.json for {job_id}"
    return json.loads(path.read_text(encoding="utf-8"))


def test_criterion_1_batch_report_order():
    """Criterion 1: batch_report.jsonl exists and jobs are in ascending job_id order."""
    rows = _load_report()
    ids = [r["job_id"] for r in rows]
    expect = _job_ids()
    assert ids == expect, f"job order {ids} != {expect}"


def test_criterion_2_recovered_schema():
    """Criterion 2: every job has recovered.json with all required keys."""
    for jid in _job_ids():
        data = _load_recovered(jid)
        missing = REQUIRED - set(data)
        assert not missing, f"{jid} missing keys {missing}"


def test_criterion_3_kv_matches_ref():
    """Criterion 3: kv matches correct journal recovery for every job."""
    exp = expected_for_jobs(JOBS)
    for jid in _job_ids():
        got = _load_recovered(jid)
        assert got["kv"] == exp[jid]["kv"], f"{jid} kv mismatch"


def test_criterion_4_boot_and_security():
    """Criterion 4: boot_slot and security_version match correct slot selection."""
    exp = expected_for_jobs(JOBS)
    for jid in _job_ids():
        got = _load_recovered(jid)
        assert got["boot_slot"] == exp[jid]["boot_slot"], f"{jid} boot_slot"
        assert got["security_version"] == exp[jid]["security_version"], f"{jid} security"


def test_criterion_5_generation():
    """Criterion 5: generation equals max modular seq among complete records."""
    exp = expected_for_jobs(JOBS)
    for jid in _job_ids():
        got = _load_recovered(jid)
        assert got["generation"] == exp[jid]["generation"], f"{jid} generation"


def test_criterion_6_anti_rollback_min():
    """Criterion 6: anti_rollback_min matches the job meta floor."""
    exp = expected_for_jobs(JOBS)
    for jid in _job_ids():
        got = _load_recovered(jid)
        assert got["anti_rollback_min"] == exp[jid]["anti_rollback_min"], f"{jid} floor"


def test_criterion_7_smoke_samples():
    """Criterion 7: sample smoke still passes on the repaired firmware."""
    proc = subprocess.run(
        [sys.executable, "/app/smoke/run_smoke.py"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
