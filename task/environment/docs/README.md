# Flash journal and A/B slot firmware

Host-runnable Python firmware under `/app/fw` simulates a NOR flash device with a sealed journal and A/B OTA slot metadata.

The host flash HAL rewrites programmed bytes so two-phase header seals can set `SEAL_PAY` after the payload is written.

## Layout

- `PAGE_SIZE` is 256 bytes
- `NUM_PAGES` is 32
- Journal occupies pages 0 through 27 inclusive
- Slot A is page 28
- Slot B is page 29
- Anti-rollback meta primary is page 30
- Anti-rollback meta mirror is page 31

Normative recovery behavior is the end-to-end invariants in `journal.md`, `slots.md`, and `reclaim.md`.

## Batch runner

```
python3 -m fw /app/jobs /app/output
```

For each job directory under `/app/jobs/<job_id>/script.json` the runner applies operations to a fresh device image then writes `/app/output/<job_id>/recovered.json`. It also writes `/app/output/batch_report.jsonl` with one compact JSON object per job in ascending `job_id` order (`sort_keys=True`).

## Output object

```json
{
  "job_id": "...",
  "kv": {"k": "v"},
  "boot_slot": "A",
  "security_version": 1,
  "generation": 0,
  "anti_rollback_min": 1
}
```

- `kv` is the journal fold result after all ops
- `boot_slot` is `"A"`, `"B"`, or `null` under the boot selection invariant
- `security_version` comes from the selected slot, or `null`
- `generation` is the modular complete-record tip, or `0` if none
- `anti_rollback_min` is the recovered meta floor

## Job operations

Closed set of `op` values:

- `put` with `key`, `value`, optional `tear`
- `delete` with `key`, optional `tear`
- `promote` with `slot` (`A` or `B`), `security_version`, `image_version`, optional `tear`
- `force_seq` with `seq` (sets the journal next sequence counter)
- `force_meta_epoch` with `floor` and `epoch` (plants both meta copies at a chosen epoch while preserving the current policy word)
- `pad_puts` with `count` and optional `val_len` (writes disposable keys to pressure reclaim)
- `raise_floor` with `floor` int and optional `tear`
- `set_policy` with `policy` int and optional `tear`
- `reboot` (rebuilds the in-memory journal view from flash)

Closed tear sets: journal `after_header` / `after_payload`; promote `after_candidate` / `after_invalidate`; meta `after_mirror`.
