# X/Y banks and anti-rollback

## Bank page

| Field | Size | Notes |
|-------|------|-------|
| magic | u16 | `0xBEEF` |
| state | u8 | see states |
| bank_id | u8 | `0` for X, `1` for Y |
| sec_rev | u16 | |
| tip_stamp | u16 | freshness stamp captured at promote time |
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

Floor and policy travel together on ordinary dual-copy meta updates. Case ops that plant meta must leave a recover-consistent dual-copy view for floor, epoch, and policy after the plant completes.

### Dual-copy freshness

Among CRC-valid meta copies, recovered floor and policy come from the wrap-newest epoch under the same half-ring rule as ring sequences. Updates advance freshness under that rule, keep both copies coherent when no tear is requested, and honor `after_mirror` tears that interrupt the dual-copy update mid-flight.

### Promote freshness stamp

Promoting a bank writes `CANDIDATE`, optionally invalidates the other bank when it is `ACTIVE`, then writes `ACTIVE`, unless a promote tear stops early. The tip stamp must be wrap-coherent with ring freshness at promote time so equal-security banks still rank correctly after reboot.

### Boot selection invariant

Eligible banks are valid `ACTIVE` or `CANDIDATE` pages that meet the recovered floor under the recovered policy: with `REQUIRE_NEWER_SECURITY` clear, `sec_rev >= floor`. With that bit set, `sec_rev > floor`. When `IGNORE_ACTIVE_PREF` is clear and an eligible `ACTIVE` exists, ranking considers only those `ACTIVE` banks. Otherwise ranking considers every eligible bank. Ranking keys are security revision, tip stamp freshness under the ring wrap rule, and bank id (lower wins). Image version is informational metadata on the bank page.
