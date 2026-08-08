"""Harbor verifier for NOR ring log / OTA bank recovery outputs."""

from __future__ import annotations

import json
import os
import tempfile
import subprocess
import sys
from pathlib import Path

OUTPUT_ROOT = Path("/app/out")
TRUSTED_SCRIPTS = Path(__file__).resolve().parent / "trusted_job_scripts"
SEAL_PATH = Path("/logs/verifier/expected.json")
SCHEMA_KEYS = frozenset(
    {
        "case_id",
        "nvs",
        "boot_bank",
        "sec_rev",
        "tip_seq",
        "sec_floor",
    }
)


def trusted_case_ids() -> list[str]:
    """Case ids taken only from verifier-private fixtures."""
    ids = [
        path.name
        for path in TRUSTED_SCRIPTS.iterdir()
        if (path / "script.json").is_file()
    ]
    return sorted(ids)


def load_sealed() -> dict:
    assert SEAL_PATH.is_file(), f"sealed expectations missing at {SEAL_PATH}"
    payload = json.loads(SEAL_PATH.read_text(encoding="utf-8"))
    cases = payload["cases"]
    assert isinstance(cases, dict), "sealed cases must be an object"
    return cases


def _require_regular_file(path: Path, label: str) -> None:
    assert path.exists(), f"{label} missing"
    assert not path.is_symlink(), f"{label} must not be a symlink"
    assert path.is_file(), f"{label} must be a regular file"


def read_suite_ledger():
    report = OUTPUT_ROOT / "suite_ledger.jsonl"
    _require_regular_file(report, "suite_ledger.jsonl")
    parsed = []
    serialized = []
    for raw in report.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        serialized.append(raw)
        parsed.append(json.loads(raw))
    return parsed, serialized


def read_state(case_id: str) -> dict:
    path = OUTPUT_ROOT / case_id / "state.json"
    _require_regular_file(path, f"state.json for {case_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def reference_by_case() -> dict:
    return load_sealed()


def test_criterion_1_suite_ledger_order():
    """Criterion 1: suite ledger exists with ascending trusted case ids."""
    rows, lines = read_suite_ledger()
    wanted = trusted_case_ids()
    got_ids = [row["case_id"] for row in rows]
    assert got_ids == wanted, f"ledger ids {got_ids} != trusted {wanted}"
    golden = reference_by_case()
    for row, line, case_id in zip(rows, lines, wanted):
        assert set(row) == SCHEMA_KEYS, f"{case_id} ledger key set wrong"
        state = read_state(case_id)
        assert row == state, f"{case_id} ledger diverges from state.json"
        assert row == golden[case_id], f"{case_id} ledger diverges from reference"
        expect_line = json.dumps(row, sort_keys=True, separators=(",", ":"))
        assert line == expect_line, f"{case_id} ledger line encoding wrong"


def test_criterion_2_state_schema():
    """Criterion 2: state.json exists with the exact required keys."""
    for case_id in trusted_case_ids():
        payload = read_state(case_id)
        assert set(payload) == SCHEMA_KEYS, f"{case_id} schema {set(payload)}"


def test_criterion_3_nvs_matches_ref():
    """Criterion 3: nvs equals independent reference recovery."""
    golden = reference_by_case()
    for case_id in trusted_case_ids():
        payload = read_state(case_id)
        assert payload["nvs"] == golden[case_id]["nvs"], f"{case_id} nvs"


def test_criterion_4_boot_and_sec_rev():
    """Criterion 4: boot_bank and sec_rev match reference policy."""
    golden = reference_by_case()
    for case_id in trusted_case_ids():
        payload = read_state(case_id)
        assert payload["boot_bank"] == golden[case_id]["boot_bank"], f"{case_id} boot"
        assert payload["sec_rev"] == golden[case_id]["sec_rev"], f"{case_id} sec_rev"


def test_criterion_5_tip_seq():
    """Criterion 5: tip_seq equals modular tip among complete records."""
    golden = reference_by_case()
    for case_id in trusted_case_ids():
        payload = read_state(case_id)
        assert payload["tip_seq"] == golden[case_id]["tip_seq"], f"{case_id} tip"


def test_criterion_6_sec_floor():
    """Criterion 6: sec_floor equals the pack meta floor."""
    golden = reference_by_case()
    for case_id in trusted_case_ids():
        payload = read_state(case_id)
        assert payload["sec_floor"] == golden[case_id]["sec_floor"], f"{case_id} floor"


def test_criterion_7_smoke_samples():
    """Criterion 7: sample packs remain green on repaired controller."""
    completed = subprocess.run(
        [sys.executable, "/tests/smoke_samples.py"],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_criterion_8_agent_norctl_rerun():
    """Criterion 8: repaired /app/norctl must reproduce reference when re-run."""
    tmp = Path(tempfile.mkdtemp(prefix="norctl_rerun_"))
    env = os.environ.copy()
    env["PYTHONPATH"] = "/app"
    completed = subprocess.run(
        [sys.executable, "-m", "norctl", str(TRUSTED_SCRIPTS), str(tmp)],
        cwd="/app",
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    golden = reference_by_case()
    for case_id in trusted_case_ids():
        path = tmp / case_id / "state.json"
        assert path.is_file(), f"norctl rerun missing state.json for {case_id}"
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload == golden[case_id], f"{case_id} norctl rerun diverges from reference"
