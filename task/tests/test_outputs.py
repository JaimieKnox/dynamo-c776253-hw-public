"""Harbor verifier for flash journal / OTA slot recovery outputs."""

from __future__ import annotations

import json
import os
import tempfile
import subprocess
import sys
from pathlib import Path

OUTPUT_ROOT = Path("/app/output")
TRUSTED_SCRIPTS = Path(__file__).resolve().parent / "trusted_job_scripts"
SEAL_PATH = Path("/logs/verifier/expected.json")
SCHEMA_KEYS = frozenset(
    {
        "job_id",
        "kv",
        "boot_slot",
        "security_version",
        "generation",
        "anti_rollback_min",
    }
)


def trusted_job_ids() -> list[str]:
    """Job ids taken only from verifier-private fixtures."""
    ids = [
        path.name
        for path in TRUSTED_SCRIPTS.iterdir()
        if (path / "script.json").is_file()
    ]
    return sorted(ids)


def load_sealed() -> dict:
    assert SEAL_PATH.is_file(), f"sealed expectations missing at {SEAL_PATH}"
    payload = json.loads(SEAL_PATH.read_text(encoding="utf-8"))
    jobs = payload["jobs"]
    assert isinstance(jobs, dict), "sealed jobs must be an object"
    return jobs


def read_batch_report():
    report = OUTPUT_ROOT / "batch_report.jsonl"
    assert report.is_file(), "batch_report.jsonl missing"
    parsed = []
    serialized = []
    for raw in report.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        serialized.append(raw)
        parsed.append(json.loads(raw))
    return parsed, serialized


def read_recovered(job_id: str) -> dict:
    path = OUTPUT_ROOT / job_id / "recovered.json"
    assert path.is_file(), f"recovered.json missing for {job_id}"
    return json.loads(path.read_text(encoding="utf-8"))


def reference_by_job() -> dict:
    return load_sealed()


def test_criterion_1_batch_report_order():
    """Criterion 1: batch report exists with ascending trusted job ids."""
    rows, lines = read_batch_report()
    wanted = trusted_job_ids()
    got_ids = [row["job_id"] for row in rows]
    assert got_ids == wanted, f"report ids {got_ids} != trusted {wanted}"
    golden = reference_by_job()
    for row, line, job_id in zip(rows, lines, wanted):
        assert set(row) == SCHEMA_KEYS, f"{job_id} report key set wrong"
        recovered = read_recovered(job_id)
        assert row == recovered, f"{job_id} report diverges from recovered.json"
        assert row == golden[job_id], f"{job_id} report diverges from reference"
        expect_line = json.dumps(row, sort_keys=True, separators=(",", ":"))
        assert line == expect_line, f"{job_id} report line encoding wrong"


def test_criterion_2_recovered_schema():
    """Criterion 2: recovered.json exists with the exact required keys."""
    for job_id in trusted_job_ids():
        payload = read_recovered(job_id)
        assert set(payload) == SCHEMA_KEYS, f"{job_id} schema {set(payload)}"


def test_criterion_3_kv_matches_ref():
    """Criterion 3: kv equals independent reference recovery."""
    golden = reference_by_job()
    for job_id in trusted_job_ids():
        payload = read_recovered(job_id)
        assert payload["kv"] == golden[job_id]["kv"], f"{job_id} kv"


def test_criterion_4_boot_and_security():
    """Criterion 4: boot_slot and security_version match reference policy."""
    golden = reference_by_job()
    for job_id in trusted_job_ids():
        payload = read_recovered(job_id)
        assert payload["boot_slot"] == golden[job_id]["boot_slot"], f"{job_id} boot"
        assert (
            payload["security_version"] == golden[job_id]["security_version"]
        ), f"{job_id} security"


def test_criterion_5_generation():
    """Criterion 5: generation equals modular tip among complete records."""
    golden = reference_by_job()
    for job_id in trusted_job_ids():
        payload = read_recovered(job_id)
        assert payload["generation"] == golden[job_id]["generation"], f"{job_id} gen"


def test_criterion_6_anti_rollback_min():
    """Criterion 6: anti_rollback_min equals the pack meta floor."""
    golden = reference_by_job()
    for job_id in trusted_job_ids():
        payload = read_recovered(job_id)
        assert (
            payload["anti_rollback_min"] == golden[job_id]["anti_rollback_min"]
        ), f"{job_id} floor"


def test_criterion_7_smoke_samples():
    """Criterion 7: sample smoke remains green on repaired firmware."""
    completed = subprocess.run(
        [sys.executable, "/app/smoke/run_smoke.py"],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_criterion_8_agent_fw_rerun():
    """Criterion 8: repaired /app/fw must reproduce reference when re-run."""
    tmp = Path(tempfile.mkdtemp(prefix="fw_rerun_"))
    env = os.environ.copy()
    env["PYTHONPATH"] = "/app"
    completed = subprocess.run(
        [sys.executable, "-m", "fw", str(TRUSTED_SCRIPTS), str(tmp)],
        cwd="/app",
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    golden = reference_by_job()
    for job_id in trusted_job_ids():
        path = tmp / job_id / "recovered.json"
        assert path.is_file(), f"fw rerun missing recovered.json for {job_id}"
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload == golden[job_id], f"{job_id} fw rerun diverges from reference"
