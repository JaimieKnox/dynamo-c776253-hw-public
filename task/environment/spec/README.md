# NOR ring log and dual-bank OTA controller

Host-runnable Python controller under `/app/norctl` simulates a NOR flash device with a sealed ring log and X/Y OTA bank metadata.

The host flash HAL rewrites programmed bytes so two-phase header seals can set `SEAL_PAY` after the payload is written.

## Layout

- `PAGE_SIZE` is 256 bytes
- `NUM_PAGES` is 32
- Ring log occupies pages 0 through 27 inclusive
- Bank X is page 28
- Bank Y is page 29
- Anti-rollback meta primary is page 30
- Anti-rollback meta mirror is page 31

Normative recovery behavior is the end-to-end invariants in `ringlog.md`, `banks.md`, and `compact.md`.

## Suite runner

```
python3 -m norctl /app/cases /app/out
```

For each case directory under `/app/cases/<case_id>/script.json` the runner applies operations to a fresh device image then writes `/app/out/<case_id>/state.json`. It also writes `/app/out/suite_ledger.jsonl` with one compact JSON object per case in ascending `case_id` order (`sort_keys=True`).

## Output object

```json
{
  "case_id": "...",
  "nvs": {"k": "v"},
  "boot_bank": "X",
  "sec_rev": 1,
  "tip_seq": 0,
  "sec_floor": 1
}
```

- `nvs` is the ring-log fold result after all ops
- `boot_bank` is `"X"`, `"Y"`, or `null` under the boot selection invariant
- `sec_rev` comes from the selected bank, or `null`
- `tip_seq` is the modular complete-record tip, or `0` if none
- `sec_floor` is the recovered meta floor

## Case operations

Closed set of `op` values:

- `put` with `key`, `value`, optional `tear`
- `delete` with `key`, optional `tear`
- `promote` with `bank` (`X` or `Y`), `sec_rev`, `image_version`, optional `tear`
- `force_seq` with `seq` (sets the ring next sequence counter)
- `force_meta_epoch` with `floor` and `epoch` (plants both meta copies at a chosen epoch and floor)
- `pad_puts` with `count` and optional `val_len` (writes disposable keys to pressure compaction)
- `raise_floor` with `floor` int and optional `tear`
- `set_policy` with `policy` int and optional `tear`
- `reboot` (rebuilds the in-memory ring view from flash)

Closed tear sets: ring `after_header` / `after_payload`, promote `after_candidate` / `after_invalidate`, and meta `after_mirror`.
