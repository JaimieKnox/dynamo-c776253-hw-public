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

## Anti-rollback meta (dual copy)

Primary meta lives on page 30. Mirror meta lives on page 31. Both copies share the same little-endian layout:

| Field | Size | Notes |
|-------|------|-------|
| magic | u16 | `0xCAFE` |
| anti_rollback_min | u16 | security floor |
| epoch | u16 | copy freshness counter |
| crc16 | u16 | CRC16-CCITT over the six bytes before `crc16` |

### Meta write order

1. Choose the next epoch as one more than the maximum epoch among copies that validate magic and CRC, wrapping in 16 bits and skipping zero so epoch never lands on `0`. Epoch maximum uses the journal half-ring newer rule.
2. Erase and program the mirror page with the new floor and epoch.
3. If tear `after_mirror` is requested, stop here. Do not program the primary page after an `after_mirror` tear.
4. Erase and program the primary page with the same floor and epoch.

### Meta read

Consider each copy that validates magic and CRC. Choose the copy whose epoch is newer under the journal half-ring rule. Return that copy's floor. If no copy validates, the floor is `0`.

### raise_floor

The `raise_floor` operation raises the security floor through that dual-copy write path, including the optional `after_mirror` tear.

## Promote phases

1. Write the target slot as `CANDIDATE` with the requested versions and current journal generation.
2. If the other slot is `ACTIVE`, rewrite it as `INVALID`.
3. Rewrite the target slot as `ACTIVE`.

Tear `after_candidate` stops after phase 1. Tear `after_invalidate` stops after phase 2.

## Boot selection

Boot selection must respect the anti-rollback floor, prefer a confirmed-active slot when one is eligible, and otherwise choose among eligible candidates by higher security version. Equal security ties break by the newer stamped generation under the journal wrap rule, then by lower slot id.

`image_version` is metadata only. Equal security and equal generation under the wrap rule fall through to lower `slot_id` only.
