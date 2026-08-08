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

Policy travels with the floor in both meta copies. Epoch plants used in tests are still ordinary meta updates with respect to policy.

### Dual-copy recovery invariant

Among copies that validate magic and CRC, recover the floor and policy from the copy whose epoch is newer under the ring wrap rule in ringlog.md. Updates program the mirror first, then the primary, with the next epoch equal to one more than the newest valid epoch under that same rule, wrapping in 16 bits and skipping zero. An `after_mirror` tear leaves only the mirror updated.

### Promote invariant

Promoting a bank writes `CANDIDATE`, optionally invalidates the other bank when it is `ACTIVE`, then writes `ACTIVE`, unless a promote tear stops early. The stamped tip equals the device ring tip that recovery would report as `tip_seq` at that moment.

### Boot selection invariant

Eligible banks are valid `ACTIVE` or `CANDIDATE` pages that meet the recovered floor under the recovered policy: with `REQUIRE_NEWER_SECURITY` clear, `sec_rev >= floor`. With that bit set, `sec_rev > floor`. When `IGNORE_ACTIVE_PREF` is clear and an eligible `ACTIVE` exists, ranking considers only those `ACTIVE` banks. Otherwise ranking considers every eligible bank. Ranking keys are security revision, tip stamp freshness under the ring wrap rule, and bank id (lower wins).
