Firmware under `/app/fw` owns a NOR flash journal plus A/B OTA slot state. Treat `/app/docs/README.md`, `/app/docs/journal.md`, `/app/docs/slots.md`, and `/app/docs/reclaim.md` as the source of truth for correct recovery.

`/app/jobs/sample_*` only covers shallow calibration. Those cases avoid mid-commit tears, avoid sequence wrap near the high end of the counter, avoid forced reclaim, avoid interrupted promote, and avoid anti-rollback rejection. The `/app/jobs/h_*` suite mixes those failure modes.

Fix the firmware until recovery agrees with the docs, then emit outputs for every directory under `/app/jobs`.

Invoke the batch as:

```
python3 -m fw /app/jobs /app/output
```

Each job must produce `/app/output/<job_id>/recovered.json` with precisely this key set:

- `job_id` (string)
- `kv` (object of string keys to string values)
- `boot_slot` (`"A"`, `"B"`, or `null`)
- `security_version` (integer or `null`)
- `generation` (integer)
- `anti_rollback_min` (integer)

Also emit `/app/output/batch_report.jsonl` with one object per job, identical keys to the recovered files, compact JSON using `sort_keys=True`, ordered by ascending `job_id`.

Success criteria:

1. `/app/output/batch_report.jsonl` is present and includes every job sorted by ascending `job_id`.
2. Each job writes `/app/output/<job_id>/recovered.json` with the full required key set.
3. Across all jobs, `kv` matches correct journal recovery through tears, sequence wrap, and post-reclaim tombstones.
4. Across all jobs, `boot_slot` and `security_version` match correct slot selection through anti-rollback, ACTIVE preference, and equal-security generation ties under the journal wrap rule.
5. Across all jobs, `generation` is the sequence tip among complete records under the journal wrap rule (use `0` when none exist).
6. Across all jobs, `anti_rollback_min` equals that job's meta floor.
7. `/app/smoke/run_smoke.py` continues to pass on the repaired firmware for `sample_*` jobs.
