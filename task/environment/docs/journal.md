# Journal records

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

A power tear may stop after the header (`after_header`) or after the payload bytes (`after_payload`) before `SEAL_PAY` is set.

## Completeness

A record is complete only when magic and `hdr_crc` are valid, both seals from the two-phase commit are present on the header, and `pay_crc` matches the payload. Incomplete records are ignored for recovery, generation, and reclaim folds.

## Sequence ordering

Sequences are 16-bit and wrap. Sequence `b` is strictly newer than `a` when the forward distance from `a` to `b` on the 16-bit ring is nonzero and at most half the ring (the usual unsigned wrap window).

Output `generation` is the complete-record sequence tip under that newer rule, or `0` if none.

## KV fold

Scan complete records in flash order. For each key keep the newest sequence. If that record is a tombstone, omit the key. Otherwise keep its value. Deletes must take effect even when reclaim never runs.
