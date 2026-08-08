# Ring log records

## Header

Little-endian fields:

| Field | Size | Notes |
|-------|------|-------|
| magic | u16 | `0xA55A` |
| flags | u8 | see flags |
| key_len | u8 | |
| val_len | u16 | |
| seq | u16 | sequence |
| hdr_crc | u16 | CRC16-CCITT over the eight bytes before `hdr_crc` |

Payload is `key || value` followed by `pay_crc` (CRC16-CCITT over the payload bytes).

## Flags

- `TOMBSTONE = 0x01`
- `SEAL_HDR = 0x02`
- `SEAL_PAY = 0x04`

## CRC

CRC16-CCITT polynomial `0x1021`, initial value `0xFFFF`, no final XOR.

## Two-phase commit

1. Program the header with `SEAL_HDR` set (and `TOMBSTONE` when deleting).
2. Program payload bytes and `pay_crc`.
3. Reprogram the header with `SEAL_PAY` also set.

A power tear may stop after the header (`after_header`) or after the payload bytes (`after_payload`) before the second seal is applied.

## Completeness

A record is durable only once the two-phase commit has fully finished for that record. Both seal phases must be present, with a valid header CRC and a matching payload CRC. Incomplete records are ignored for recovery, tip selection, and compaction folds.

## Write cursor

Append placement walks programmed headers in flash order and continues after the last header region that occupies flash from a programmed header, even when that header never finished both seal phases. Completeness still decides which records participate in NVS fold and tip selection.

Reported `tip_seq`, promote tip stamps, and append `next_seq` allocation share one ring tip: the newest complete sequence under the wrap rule below (or `0` when none). `next_seq` is one more than that tip in 16 bits, skipping zero. After `reboot` and after `force_seq` plants, reporting and later appends stay on that same tip rule, including after compaction rewrite returns.

Compaction erase and rewrite must leave append allocation coherent with the post-rewrite wrap tip. See compact.md.

## Sequence ordering

Sequences are 16-bit and wrap. Every consumer of "newer" (NVS fold, compaction fold, boot tip ties, meta epoch selection, the ring tip used to derive `next_seq`, and output `tip_seq`) must use the same half-ring forward window on the 16-bit counter: sequence `b` is newer than sequence `a` only when the forward distance `((b - a) & 0xFFFF)` lies in the inclusive range `1` through `32767`. When that forward distance is exactly `32768`, neither direction is newer under this window.

## NVS fold

Scan complete records in flash order. For each key keep the newest sequence under the wrap rule above. If that record is a tombstone, omit the key. Otherwise keep its value. Deletes must take effect even when compaction never runs.
