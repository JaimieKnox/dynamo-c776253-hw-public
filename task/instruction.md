You are repairing embedded recovery code for a dual-bank OTA device.

Code lives in `/app/norctl`. Correct behavior is defined only by `/app/spec/README.md`, `/app/spec/ringlog.md`, `/app/spec/banks.md`, and `/app/spec/compact.md`. Do not invent rules that conflict with those documents.

Sequence freshness follows the ring wrap rule in `/app/spec/ringlog.md`. Apply that same rule wherever recovery compares sequences.

Case packs sit under `/app/cases`. The `sample_*` packs stay green on the shipped tree. The `h_*` packs exercise end-to-end recovery invariants from `/app/spec`.

Bring controller recovery in line with the spec, then generate outputs for every pack under `/app/cases` by running:

```
PYTHONPATH=/app python3 -m norctl /app/cases /app/out
```

Create `/app/out/<case_id>/state.json` for each pack. The JSON object must contain exactly:

- `case_id` as a string
- `nvs` as a string-to-string object
- `boot_bank` as `"X"`, `"Y"`, or `null`
- `sec_rev` as an integer or `null`
- `tip_seq` as an integer
- `sec_floor` as an integer

Create `/app/out/suite_ledger.jsonl` as well. Each line is one case object with the same keys, written with compact separators and `sort_keys=True`, and lines must appear in ascending `case_id` order.

Graded checks:

1. The suite ledger file exists and covers every case pack under `/app/cases` in ascending `case_id` order.
2. Every pack has a state file with the exact required key set.
3. `nvs` matches `/app/spec` for each pack after ring fold and compaction.
4. `boot_bank` and `sec_rev` match `/app/spec/banks.md` for each pack.
5. `tip_seq` is the modular sequence tip of complete records, or `0` when there are none.
6. `sec_floor` matches each pack meta floor after dual-copy recovery.
7. The `sample_*` packs still recover correctly after the repair (sample smoke stays green).
8. The repaired code under `/app/norctl` must itself reproduce the graded recovery outputs when re-run against the case packs.
