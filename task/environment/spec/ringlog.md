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

## Crash-safe append placement

After any tear, reboot, or reclaim rewrite, tip reporting and write-cursor placement must stay coherent with crash-safe append placement: the next sealed append lands in erased flash beyond every already-programmed well-formed header region. Later appends stay clear of any torn header that still occupies flash. Durable completeness still gates which records contribute to tip and NVS fold.

## Tip and allocation coherence

Reported tip_seq in recovery outputs is the wrap-newest complete sequence under the half-ring rule, or `0` when none. The next assigned sequence is one more than that tip in 16 bits, skipping zero. Tip reporting and append allocation stay mutually consistent across reboot, reclaim rewrite, and `force_seq` plants.

## Sequence ordering

Sequences are 16-bit and wrap. Every consumer of "newer" (NVS fold, compaction fold, boot tip ties, meta epoch selection, tip reporting, and append allocation derived from tip) must use the same half-ring forward window on the 16-bit counter: sequence `b` is newer than sequence `a` only when the forward distance `((b - a) & 0xFFFF)` lies in the inclusive range `1` through `32767`. When that forward distance is exactly `32768`, neither direction is newer under this window.

## NVS fold

Among complete records for each key, keep the wrap-newest value under the half-ring rule above. A wrap-newer tombstone removes the key. Deletes must take effect even when compaction never runs.
