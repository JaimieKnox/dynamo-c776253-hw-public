# NOR ring log and dual-bank repair

Harbor task under `task/` for repairing a host-simulated NOR flash controller that stores a sealed ring log and X/Y OTA bank metadata.

## Overview

The agent works in `/app` with controller code under `/app/norctl` and normative specs under `/app/spec`. Sample and hard cases live under `/app/cases`. The goal is to fix recovery so torn commits, sequence wrap, compaction, promote tears, dual-copy anti-rollback meta, and tip ranking behave as documented, then emit recovered state for every case.

Required outputs:

- `/app/out/<case_id>/state.json` for each case
- `/app/out/suite_ledger.jsonl` covering all cases in ascending `case_id` order

Suite entrypoint:

```bash
python3 -m norctl /app/cases /app/out
```

## Approach

The reference solution replaces the defective modules with corrected implementations, then runs the suite driver:

1. Copy fixed `ringlog.py`, `compact.py`, and `banks.py` into `/app/norctl`.
2. Require sealed records (`SEAL_HDR` and `SEAL_PAY`) with matching payload CRC before they count as live.
3. Honor ring tear phases `after_header` and `after_payload`, and promote tear phases `after_candidate` and `after_invalidate`.
4. Recover NVS state, boot bank, security revision, tip sequence, and anti-rollback floor per case specs.
5. Write per-case JSON plus the sorted suite ledger.

## Environment

- Image: `task/environment/Dockerfile` on digest-pinned Ubuntu 24.04
- Runtime: Python 3 with `pytest` and `pytest-json-ctrf` baked in
- Baked content: `/app/spec`, `/app/norctl`, `/app/cases`, `/app/smoke`
- Not baked: `task/solution/` and `task/tests/` (Harbor mounts those only for oracle and verify)

## Verification

From `task/`:

```bash
harbor run -p . -a oracle   # expect reward 1.0
harbor run -p . --agent nop # expect reward 0.0
```

`tests/test.sh` always exits 0 and writes `1` or `0` to `/logs/verifier/reward.txt` based on pytest against `tests/test_outputs.py` and `tests/ref_model.py`. Checks cover suite ledger ordering, state JSON keys, ring and bank recovery against the reference model, and smoke on `sample_*` cases.
