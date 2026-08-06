You are repairing embedded recovery code for a dual-bank OTA device.

Code lives in `/app/fw`. Correct behavior is defined only by `/app/docs/README.md`, `/app/docs/journal.md`, `/app/docs/slots.md`, and `/app/docs/reclaim.md`. Do not invent rules that conflict with those documents.

Under the journal wrap rule in `/app/docs/journal.md`, a sequence is newer only on a forward 16-bit distance of `1` through `32767`. An exact antipode pair (forward distance `32768`) is not newer. Retain the already-selected sequence for KV fold, generation tip, meta epoch selection, and boot generation ties.

Job packs sit under `/app/jobs`. The `sample_*` packs stay green on the shipped tree. The `h_*` packs combine journal recovery, slot promotion, and dual-copy meta under the rules in `/app/docs`.

Bring firmware recovery in line with the docs, then generate outputs for every pack under `/app/jobs` by running:

```
python3 -m fw /app/jobs /app/output
```

Create `/app/output/<job_id>/recovered.json` for each pack. The JSON object must contain exactly:

- `job_id` as a string
- `kv` as a string-to-string object
- `boot_slot` as `"A"`, `"B"`, or `null`
- `security_version` as an integer or `null`
- `generation` as an integer
- `anti_rollback_min` as an integer

Create `/app/output/batch_report.jsonl` as well. Each line is one job object with the same keys, written with compact separators and `sort_keys=True`, and lines must appear in ascending `job_id` order.

Graded checks:

1. The batch report file exists and covers every pack in ascending `job_id` order.
2. Every pack has a recovered file with the exact required key set.
3. `kv` matches `/app/docs` for each pack after journal fold and reclaim.
4. `boot_slot` and `security_version` match `/app/docs/slots.md` for each pack.
5. `generation` is the modular sequence tip of complete records, or `0` when there are none.
6. `anti_rollback_min` matches each pack meta floor after dual-copy recovery.
7. `/app/smoke/run_smoke.py` still succeeds for `sample_*` after the repair.
8. The repaired code under `/app/fw` must itself reproduce the graded recovery outputs when re-run against the job packs.
