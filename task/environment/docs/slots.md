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
| policy | u16 | boot policy bits |
| crc16 | u16 | CRC16-CCITT over the eight bytes before `crc16` |

### Policy bits

- bit 0 (`0x0001`) `REQUIRE_NEWER_SECURITY`: an eligible slot must have `security_version` strictly greater than the recovered floor (equality is not enough).
- bit 1 (`0x0002`) `IGNORE_ACTIVE_PREF`: do not prefer ACTIVE; rank all eligible ACTIVE and CANDIDATE slots together by security, then generation, then slot id.

When a bit is clear, the default boot rules apply for that concern. Policy is carried in both meta copies and selected with the same epoch-newer copy as the floor.

### Meta write order

1. Choose the next epoch as one more than the maximum epoch among copies that validate magic and CRC, wrapping in 16 bits and skipping zero so epoch never lands on `0`. Epoch maximum uses the journal half-ring newer rule.
2. Erase and program the mirror page with the new floor, epoch, and current policy word.
3. If tear `after_mirror` is requested, stop here. Do not program the primary page after an `after_mirror` tear.
4. Erase and program the primary page with the same floor, epoch, and policy word.

### Meta read

Consider each copy that validates magic and CRC. Choose the copy whose epoch is newer under the journal half-ring rule. Return that copy's floor and policy. If no copy validates, the floor is `0` and policy is `0`.

### raise_floor and set_policy

The `raise_floor` operation raises the security floor through that dual-copy write path, including the optional `after_mirror` tear, preserving the current policy word.

The `set_policy` operation writes a new policy word through the same dual-copy path, preserving the current floor.

## Promote phases

The generation field stamped into the slot page is the modular complete-record tip from the journal at promote time (the same tip used for output `generation`), not the flash-order last complete sequence and not `image_version`.

1. Write the target slot as `CANDIDATE` with the requested versions and current journal generation.
2. If the other slot is `ACTIVE`, rewrite it as `INVALID`.
3. Rewrite the target slot as `ACTIVE`.

Tear `after_candidate` stops after phase 1. Tear `after_invalidate` stops after phase 2.

## Boot selection

Boot selection must respect the anti-rollback floor (a slot is eligible only when its `security_version` is greater than or equal to the recovered floor), prefer a confirmed-active slot when one is eligible, and otherwise choose among eligible candidates by higher security version. Equal security ties break by the newer stamped generation under the journal wrap rule, then by lower slot id.

`image_version` is metadata only and must not affect boot ranking. Equal security ties break by newer stamped generation under the journal wrap rule, then by lower `slot_id` only.
