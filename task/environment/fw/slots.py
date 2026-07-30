"""A/B OTA slot metadata and boot selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .crc16 import crc16_ccitt
from .flash_hal import META_PAGE, PAGE_SIZE, SLOT_A_PAGE, SLOT_B_PAGE, Flash

MAGIC_SLOT = 0xBEEF
MAGIC_META = 0xCAFE

EMPTY = 0
CANDIDATE = 1
ACTIVE = 2
INVALID = 3

SLOT_ID = {"A": 0, "B": 1}
ID_SLOT = {0: "A", 1: "B"}


@dataclass
class SlotInfo:
    state: int
    slot_id: int
    security_version: int
    generation: int
    image_version: int
    valid: bool


def _pack_slot(
    state: int,
    slot_id: int,
    security_version: int,
    generation: int,
    image_version: int,
) -> bytes:
    body = bytes(
        [
            MAGIC_SLOT & 0xFF,
            (MAGIC_SLOT >> 8) & 0xFF,
            state & 0xFF,
            slot_id & 0xFF,
            security_version & 0xFF,
            (security_version >> 8) & 0xFF,
            generation & 0xFF,
            (generation >> 8) & 0xFF,
            image_version & 0xFF,
            (image_version >> 8) & 0xFF,
            (image_version >> 16) & 0xFF,
            (image_version >> 24) & 0xFF,
        ]
    )
    c = crc16_ccitt(body)
    return body + bytes([c & 0xFF, (c >> 8) & 0xFF])


def write_slot(flash: Flash, which: str, info: SlotInfo) -> None:
    page = SLOT_A_PAGE if which == "A" else SLOT_B_PAGE
    flash.erase_page(page)
    blob = _pack_slot(
        info.state,
        info.slot_id,
        info.security_version,
        info.generation,
        info.image_version,
    )
    flash.program(page * PAGE_SIZE, blob)


def read_slot(flash: Flash, which: str) -> SlotInfo:
    page = SLOT_A_PAGE if which == "A" else SLOT_B_PAGE
    raw = flash.read(page * PAGE_SIZE, 14)
    magic = raw[0] | (raw[1] << 8)
    if magic != MAGIC_SLOT:
        return SlotInfo(EMPTY, SLOT_ID[which], 0, 0, 0, False)
    state = raw[2]
    slot_id = raw[3]
    sec = raw[4] | (raw[5] << 8)
    gen = raw[6] | (raw[7] << 8)
    img = raw[8] | (raw[9] << 8) | (raw[10] << 16) | (raw[11] << 24)
    crc = raw[12] | (raw[13] << 8)
    ok = crc16_ccitt(raw[:12]) == crc
    return SlotInfo(state, slot_id, sec, gen, img, ok)


def write_meta(flash: Flash, anti_rollback_min: int) -> None:
    flash.erase_page(META_PAGE)
    body = bytes(
        [
            MAGIC_META & 0xFF,
            (MAGIC_META >> 8) & 0xFF,
            anti_rollback_min & 0xFF,
            (anti_rollback_min >> 8) & 0xFF,
        ]
    )
    c = crc16_ccitt(body)
    flash.program(META_PAGE * PAGE_SIZE, body + bytes([c & 0xFF, (c >> 8) & 0xFF]))


def read_meta(flash: Flash) -> int:
    raw = flash.read(META_PAGE * PAGE_SIZE, 6)
    magic = raw[0] | (raw[1] << 8)
    if magic != MAGIC_META:
        return 0
    floor = raw[2] | (raw[3] << 8)
    crc = raw[4] | (raw[5] << 8)
    if crc16_ccitt(raw[:4]) != crc:
        return 0
    return floor


def select_boot_slot(flash: Flash) -> Tuple[Optional[str], Optional[int], int]:
    """Return (slot_name_or_None, security_version_or_None, anti_rollback_min)."""
    floor = read_meta(flash)
    candidates: List[Tuple[str, SlotInfo]] = []
    for name in ("A", "B"):
        info = read_slot(flash, name)
        if not info.valid:
            continue
        if info.state in (ACTIVE, CANDIDATE):
            candidates.append((name, info))
    if not candidates:
        return None, None, floor
    candidates.sort(key=lambda x: (-x[1].image_version, x[1].slot_id))
    name, info = candidates[0]
    return name, info.security_version, floor


def promote(
    flash: Flash,
    which: str,
    security_version: int,
    image_version: int,
    generation: int,
    tear: Optional[str] = None,
) -> None:
    """Promote slot with optional tear points.

    Phases: write CANDIDATE, invalidate other ACTIVE, mark ACTIVE.
    """
    other = "B" if which == "A" else "A"
    sid = SLOT_ID[which]
    cand = SlotInfo(CANDIDATE, sid, security_version, generation, image_version, True)
    write_slot(flash, which, cand)
    if tear == "after_candidate":
        return
    o = read_slot(flash, other)
    if o.valid and o.state == ACTIVE:
        write_slot(
            flash,
            other,
            SlotInfo(INVALID, o.slot_id, o.security_version, o.generation, o.image_version, True),
        )
    if tear == "after_invalidate":
        return
    write_slot(
        flash,
        which,
        SlotInfo(ACTIVE, sid, security_version, generation, image_version, True),
    )
