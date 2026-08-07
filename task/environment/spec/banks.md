# X/Y banks and anti-rollback

## Bank page

| Field | Size | Notes |
|-------|------|-------|
| magic | u16 | `0xBEEF` |
| state | u8 | see states |
| bank_id | u8 | `0` for X, `1` for Y |
| sec_rev | u16 | |
| tip_stamp | u16 | ring tip at promote time |
| image_version | u32 | informational build stamp |
| crc16 | u16 | CRC16-CCITT over the twelve bytes before `crc16` |

## States (closed set)

- `EMPTY = 0`
- `CANDIDATE = 1`
- `ACTIVE = 2`
- `INVALID = 3`

A bank page is usable only when magic and CRC validate.

## Anti-rollback meta (dual copy)

Primary meta lives on page 30. Mirror meta lives on page 31.

| Field | Size | Notes |
|-------|------|-------|
| magic | u16 | `0xCAFE` |
| sec_floor | u16 | security floor |
| epoch | u16 | copy freshness counter |
| policy | u16 | boot policy bits |
| crc16 | u16 | CRC16-CCITT over the eight bytes before `crc16` |

### Policy bits

| Bit | Value | Name |
|-----|-------|------|
| 0 | `0x0001` | `REQUIRE_NEWER_SECURITY` |
| 1 | `0x0002` | `IGNORE_ACTIVE_PREF` |

Policy travels with the floor in both meta copies. Planting a test epoch pair preserves the current policy word.

### Dual-copy recovery invariant

Among copies that validate magic and CRC, the recovered floor and policy are those of the copy whose epoch is newer under the ring half-ring rule. A larger raw 16-bit integer is not automatically newer across wrap. Use the ring wrap rule from ringlog.md. Updates program the mirror first, then the primary, with the next epoch equal to one more than the half-ring-maximum valid epoch, wrapping in 16 bits and skipping zero. An `after_mirror` tear leaves only the mirror updated.

### Promote invariant

Promoting a bank writes `CANDIDATE`, optionally invalidates the other bank when it is `ACTIVE`, then writes `ACTIVE`, unless a promote tear stops early. The stamped tip is the modular complete-record ring tip supplied for that promote, matching output `tip_seq` at that moment. Do not replace that tip with a raw integer maximum over flash sequences when the wrap rule disagrees.

### Boot selection invariant

Eligible banks are valid `ACTIVE` or `CANDIDATE` pages that meet the recovered floor under the recovered policy: with `REQUIRE_NEWER_SECURITY` clear, `sec_rev >= floor`; with that bit set, `sec_rev > floor`. When `IGNORE_ACTIVE_PREF` is clear and an eligible `ACTIVE` exists, ranking considers only those `ACTIVE` banks. Otherwise ranking considers every eligible bank. Order by higher `sec_rev`, then newer stamped tip under the ring half-ring rule, then lower `bank_id`. A larger raw 16-bit stamped tip is not automatically newer across wrap. Use the ring wrap rule from ringlog.md for tip ties just as for meta epochs.
