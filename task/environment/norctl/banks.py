"""X/Y OTA bank metadata and boot selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .crc16 import crc16_ccitt
from .flash_hal import META_MIRROR_PAGE, META_PAGE, PAGE_SIZE, BANK_X_PAGE, BANK_Y_PAGE, Flash

MAGIC_SLOT = 0xBEEF
MAGIC_META = 0xCAFE
EMPTY, CANDIDATE, ACTIVE, INVALID = 0, 1, 2, 3
BANK_ID = {"X": 0, "Y": 1}
REQUIRE_NEWER_SECURITY = 0x0001
IGNORE_ACTIVE_PREF = 0x0002


@dataclass
class BankInfo:
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


def _unpack_slot(raw: bytes) -> BankInfo:
    if len(raw) < 14:
        return BankInfo(EMPTY, 0, 0, 0, 0, False)
    magic = raw[0] | (raw[1] << 8)
    if magic != MAGIC_SLOT:
        return BankInfo(EMPTY, 0, 0, 0, 0, False)
    body, crc = raw[:12], raw[12] | (raw[13] << 8)
    if crc16_ccitt(body) != crc:
        return BankInfo(EMPTY, 0, 0, 0, 0, False)
    return BankInfo(
        raw[2],
        raw[3],
        raw[4] | (raw[5] << 8),
        raw[6] | (raw[7] << 8),
        raw[8] | (raw[9] << 8) | (raw[10] << 16) | (raw[11] << 24),
        True,
    )


def write_bank(flash: Flash, which: str, info: BankInfo) -> None:
    page = BANK_X_PAGE if which == "X" else BANK_Y_PAGE
    flash.erase_page(page)
    flash.program(page * PAGE_SIZE, _pack_slot(info.state, info.slot_id, info.security_version, info.generation, info.image_version))


def read_bank(flash: Flash, which: str) -> BankInfo:
    page = BANK_X_PAGE if which == "X" else BANK_Y_PAGE
    return _unpack_slot(flash.read(page * PAGE_SIZE, 14))


def _pack_meta(floor: int, epoch: int, policy: int) -> bytes:
    body = bytes(
        [
            MAGIC_META & 0xFF,
            (MAGIC_META >> 8) & 0xFF,
            floor & 0xFF,
            (floor >> 8) & 0xFF,
            epoch & 0xFF,
            (epoch >> 8) & 0xFF,
            policy & 0xFF,
            (policy >> 8) & 0xFF,
        ]
    )
    c = crc16_ccitt(body)
    return body + bytes([c & 0xFF, (c >> 8) & 0xFF])


def _unpack_meta(raw: bytes):
    if len(raw) < 10:
        return None
    magic = raw[0] | (raw[1] << 8)
    if magic != MAGIC_META:
        return None
    if crc16_ccitt(raw[:8]) != (raw[8] | (raw[9] << 8)):
        return None
    floor = raw[2] | (raw[3] << 8)
    epoch = raw[4] | (raw[5] << 8)
    policy = raw[6] | (raw[7] << 8)
    return floor, epoch, policy


def _gen_newer(a: int, b: int) -> bool:
    delta = (b - a) & 0xFFFF
    return 1 <= delta <= 32767


def _program_meta_page(flash: Flash, page: int, floor: int, epoch: int, policy: int) -> None:
    flash.erase_page(page)
    flash.program(page * PAGE_SIZE, _pack_meta(floor, epoch, policy))


def _read_meta_full(flash: Flash):
    best = None  # (epoch, floor, policy)
    for page in (META_PAGE, META_MIRROR_PAGE):
        parsed = _unpack_meta(flash.read(page * PAGE_SIZE, 10))
        if parsed is None:
            continue
        floor, epoch, policy = parsed
        if best is None or epoch > best[0]:
            best = (epoch, floor, policy)
    if best is None:
        return 0, 0
    return best[1], best[2]


def write_meta(flash: Flash, floor: int, policy: Optional[int] = None, tear: Optional[str] = None) -> None:
    cur_floor, cur_policy = _read_meta_full(flash)
    if policy is None:
        policy = cur_policy
    max_epoch = 0
    for page in (META_PAGE, META_MIRROR_PAGE):
        parsed = _unpack_meta(flash.read(page * PAGE_SIZE, 10))
        if parsed is None:
            continue
        epoch = parsed[1]
        if max_epoch == 0 or epoch > max_epoch:
            max_epoch = epoch
    next_epoch = (max_epoch + 1) & 0xFFFF
    if next_epoch == 0:
        next_epoch = 1
    _program_meta_page(flash, META_MIRROR_PAGE, floor, next_epoch, policy & 0xFFFF)
    if tear == "after_mirror":
        return
    _program_meta_page(flash, META_PAGE, floor, next_epoch, policy & 0xFFFF)


def read_meta(flash: Flash) -> int:
    floor, _policy = _read_meta_full(flash)
    return floor


def read_policy(flash: Flash) -> int:
    _floor, policy = _read_meta_full(flash)
    return policy


def select_boot_bank(flash: Flash) -> Tuple[Optional[str], Optional[int], int]:
    floor, policy = _read_meta_full(flash)
    pool: List[Tuple[str, BankInfo]] = []
    for name in ("X", "Y"):
        info = read_bank(flash, name)
        if not info.valid:
            continue
        if info.state not in (ACTIVE, CANDIDATE):
            continue
        if policy & REQUIRE_NEWER_SECURITY:
            if info.security_version <= floor:
                continue
        else:
            if info.security_version < floor:
                continue
        pool.append((name, info))
    if not pool:
        return None, None, floor
    if policy & IGNORE_ACTIVE_PREF:
        chosen = pool
    else:
        active = [(n, i) for n, i in pool if i.state == ACTIVE]
        chosen = active if active else pool
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
    other = "Y" if which == "X" else "X"
    sid = BANK_ID[which]
    cand = BankInfo(CANDIDATE, sid, security_version, generation, image_version, True)
    write_bank(flash, which, cand)
    if tear == "after_candidate":
        return
    o = read_bank(flash, other)
    if o.valid and o.state == ACTIVE:
        write_bank(
            flash,
            other,
            BankInfo(INVALID, o.slot_id, o.security_version, o.generation, o.image_version, True),
        )
    if tear == "after_invalidate":
        return
    write_bank(
        flash,
        which,
        BankInfo(ACTIVE, sid, security_version, generation, image_version, True),
    )
