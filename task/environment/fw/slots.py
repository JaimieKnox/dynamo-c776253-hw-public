"""A/B OTA slot metadata and boot selection ."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .crc16 import crc16_ccitt
from .flash_hal import META_MIRROR_PAGE, META_PAGE, PAGE_SIZE, SLOT_A_PAGE, SLOT_B_PAGE, Flash

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


def _pack_meta(floor: int, epoch: int) -> bytes:
    body = bytes(
        [
            MAGIC_META & 0xFF,
            (MAGIC_META >> 8) & 0xFF,
            floor & 0xFF,
            (floor >> 8) & 0xFF,
            epoch & 0xFF,
            (epoch >> 8) & 0xFF,
        ]
    )
    c = crc16_ccitt(body)
    return body + bytes([c & 0xFF, (c >> 8) & 0xFF])


def _unpack_meta(raw: bytes) -> Optional[Tuple[int, int]]:
    if len(raw) < 8:
        return None
    magic = raw[0] | (raw[1] << 8)
    if magic != MAGIC_META:
        return None
    floor = raw[2] | (raw[3] << 8)
    epoch = raw[4] | (raw[5] << 8)
    crc = raw[6] | (raw[7] << 8)
    if crc16_ccitt(raw[:6]) != crc:
        return None
    return floor, epoch


def _gen_newer(a: int, b: int) -> bool:
    delta = (b - a) & 0xFFFF
    return 1 <= delta <= 32768


def _program_meta_page(flash: Flash, page: int, floor: int, epoch: int) -> None:
    flash.erase_page(page)
    flash.program(page * PAGE_SIZE, _pack_meta(floor, epoch))


def write_meta(flash: Flash, floor: int, tear: Optional[str] = None) -> None:
    max_epoch = 0
    for page in (META_PAGE, META_MIRROR_PAGE):
        parsed = _unpack_meta(flash.read(page * PAGE_SIZE, 8))
        if parsed is None:
            continue
        epoch = parsed[1]
        if epoch > max_epoch:
            max_epoch = epoch
    next_epoch = (max_epoch + 1) & 0xFFFF
    if next_epoch == 0:
        next_epoch = 1
    _program_meta_page(flash, META_MIRROR_PAGE, floor, next_epoch)
    if tear == "after_mirror":
        return
    _program_meta_page(flash, META_PAGE, floor, next_epoch)


def read_meta(flash: Flash) -> int:
    best_floor = None
    best_epoch = None
    for page in (META_PAGE, META_MIRROR_PAGE):
        parsed = _unpack_meta(flash.read(page * PAGE_SIZE, 8))
        if parsed is None:
            continue
        floor, epoch = parsed
        if best_epoch is None or epoch > best_epoch:
            best_epoch = epoch
            best_floor = floor
    return 0 if best_floor is None else best_floor


def select_boot_slot(flash: Flash) -> Tuple[Optional[str], Optional[int], int]:
    """Select boot slot among eligible ACTIVE/CANDIDATE pages."""
    floor = read_meta(flash)
    pool: List[Tuple[str, SlotInfo]] = []
    for name in ("A", "B"):
        info = read_slot(flash, name)
        if not info.valid:
            continue
        if info.state not in (ACTIVE, CANDIDATE):
            continue
        if info.security_version < floor:
            continue
        pool.append((name, info))
    if not pool:
        return None, None, floor
    chosen = pool
    best_name, best = chosen[0]
    for name, info in chosen[1:]:
        if info.security_version > best.security_version:
            best_name, best = name, info
            continue
        if info.security_version < best.security_version:
            continue
        if _gen_newer(best.generation, info.generation):
            best_name, best = name, info
            continue
        if _gen_newer(info.generation, best.generation):
            continue
        if info.slot_id < best.slot_id:
            best_name, best = name, info
    return best_name, best.security_version, floor


def promote(
    flash: Flash,
    which: str,
    security_version: int,
    image_version: int,
    generation: int,
    tear: Optional[str] = None,
) -> None:
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
