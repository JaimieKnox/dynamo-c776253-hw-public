# A/B slots and anti-rollback

## Slot page

| Field | Size | Notes |
|-------|------|-------|
| magic | u16 | `0xBEEF` |
| state | u8 | see states |
| slot_id | u8 | `0` for A, `1` for B |
| security_version | u16 | |
| generation | u16 | copied from journal generation at promote time |
| image_version | u32 | |
| crc16 | u16 | CRC16-CCITT over the twelve bytes before `crc16` |

## States (closed set)

- `EMPTY = 0`
- `CANDIDATE = 1`
- `ACTIVE = 2`
- `INVALID = 3`

A slot page is usable only when magic and CRC validate.

## Meta page

| Field | Size | Notes |
|-------|------|-------|
| magic | u16 | `0xCAFE` |
| anti_rollback_min | u16 | security floor |
| crc16 | u16 | CRC16-CCITT over the four bytes before `crc16` |

## Promote phases

1. Write the target slot as `CANDIDATE` with the requested versions and current journal generation.
2. If the other slot is `ACTIVE`, rewrite it as `INVALID`.
3. Rewrite the target slot as `ACTIVE`.

Tear `after_candidate` stops after phase 1. Tear `after_invalidate` stops after phase 2.

## Boot selection

1. Read `anti_rollback_min` from meta (`0` if meta invalid).
2. Build a pool of slots whose page is valid, whose state is `ACTIVE` or `CANDIDATE`, and whose `security_version >= anti_rollback_min`.
3. If the pool is empty, boot slot is `null` and `security_version` is `null`.
4. If any pool member is `ACTIVE`, restrict the pool to those `ACTIVE` slots.
5. Sort the resulting pool by `(-security_version, -generation, slot_id)` ascending key order and pick the first.

`image_version` is metadata only and must not decide boot selection.
