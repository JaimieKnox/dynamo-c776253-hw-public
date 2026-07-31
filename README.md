# Flash journal and A/B slot recovery

Harbor task under `task/` for repairing host-simulated NOR flash firmware that stores a sealed journal and A/B OTA slot metadata.

## Overview

The agent works in `/app` with firmware under `/app/fw` and normative docs under `/app/docs`. Sample and hard jobs live under `/app/jobs`. The goal is to fix recovery so torn commits, sequence wrap, reclaim, promote tears, and anti-rollback behave as documented, then emit recovered state for every job.

Required outputs:

- `/app/output/<job_id>/recovered.json` for each job
- `/app/output/batch_report.jsonl` covering all jobs in ascending `job_id` order

Batch entrypoint:

```bash
python3 -m fw /app/jobs /app/output
```

## Approach

The reference solution replaces buggy modules with corrected implementations, then runs the batch driver:

1. Copy fixed `journal.py`, `reclaim.py`, and `slots.py` into `/app/fw`.
2. Require sealed records (`SEAL_HDR` and `SEAL_PAY`) with matching payload CRC before they count as live.
3. Honor journal tear phases `after_header` and `after_payload`, and promote tear phases `after_candidate` and `after_invalidate`.
4. Recover KV state, boot slot, security version, generation, and anti-rollback floor per job docs.
5. Write per-job JSON plus the sorted batch report.

## Environment

- Image: `task/environment/Dockerfile` on digest-pinned Ubuntu 24.04
- Runtime: Python 3 with `pytest` and `pytest-json-ctrf` baked in
- Baked content: `/app/docs`, `/app/fw`, `/app/jobs`, `/app/smoke`
- Not baked: `task/solution/` and `task/tests/` (Harbor mounts those only for oracle and verify)

## Verification

From `task/`:

```bash
harbor run -p . -a oracle   # expect reward 1.0
harbor run -p . --agent nop # expect reward 0.0
```

`tests/test.sh` always exits 0 and writes `1` or `0` to `/logs/verifier/reward.txt` based on pytest against `tests/test_outputs.py` and `tests/ref_model.py`. Checks cover batch report ordering, recovered JSON keys, journal and slot recovery against the reference model, and smoke on `sample_*` jobs.
