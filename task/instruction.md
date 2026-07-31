The device firmware under `/app/fw` persists a NOR flash journal and A/B OTA slot metadata. Normative behavior is documented in `/app/docs/README.md`, `/app/docs/journal.md`, `/app/docs/slots.md`, and `/app/docs/reclaim.md`.

Sample jobs under `/app/jobs/sample_*` are narrow calibration cases. They never tear mid-commit, never wrap the sequence counter near its top, never force reclaim, never interrupt promote, and never rely on anti-rollback rejection. Harder jobs under `/app/jobs/h_*` exercise those paths, including reclaim that lands across a sequence wrap.

Repair the firmware so recovery matches the docs, then produce batch outputs for every job in `/app/jobs`.

Run the batch with:

```
python3 -m fw /app/jobs /app/output
```

For each job write `/app/output/<job_id>/recovered.json` with exactly these keys:

- `job_id` (string)
- `kv` (object mapping string keys to string values)
- `boot_slot` (`"A"`, `"B"`, or `null`)
- `security_version` (integer or `null`)
- `generation` (integer)
- `anti_rollback_min` (integer)

Also write `/app/output/batch_report.jsonl`: one JSON object per job, same keys as each recovered file, compact form with `sort_keys=True`, jobs in ascending `job_id` order.

Success criteria:

1. `/app/output/batch_report.jsonl` exists and lists every job in ascending `job_id` order.
2. Every job has `/app/output/<job_id>/recovered.json` containing all required keys.
3. For every job, `kv` matches correct journal recovery including tears, sequence wrap, and tombstones after reclaim.
4. For every job, `boot_slot` and `security_version` match correct slot selection including anti-rollback, ACTIVE preference, and modular generation ranking on ties.
5. For every job, `generation` equals the modular sequence tip among complete records under the journal newer rule (or `0` if none).
6. For every job, `anti_rollback_min` matches the meta floor used by that job.
7. `/app/smoke/run_smoke.py` still passes against the repaired firmware for `sample_*` jobs.
