"""Independent correct recovery model. Does not import /app/norctl."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cmp_to_key
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

PAGE_SIZE = 256
NUM_PAGES = 32
RING_PAGES = 28
BANK_X_PAGE = 28
BANK_Y_PAGE = 29
META_PAGE = 30
META_MIRROR_PAGE = 31

MAGIC = 0xA55A
HDR_SIZE = 10
TOMBSTONE = 0x01
SEAL_HDR = 0x02
SEAL_PAY = 0x04

MAGIC_SLOT = 0xBEEF
MAGIC_META = 0xCAFE
EMPTY = 0
CANDIDATE = 1
ACTIVE = 2
INVALID = 3
BANK_ID = {"X": 0, "Y": 1}


def crc16_ccitt(data: bytes, init: int = 0xFFFF) -> int:
    crc = init & 0xFFFF
    for b in data:
        crc ^= (b << 8) & 0xFFFF
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def newer_seq(a: int, b: int) -> bool:
    delta = (b - a) & 0xFFFF
    return 1 <= delta <= 32767


class Flash:
    def __init__(self) -> None:
        self.mem = bytearray([0xFF] * (PAGE_SIZE * NUM_PAGES))

    def read(self, addr: int, n: int) -> bytes:
        return bytes(self.mem[addr : addr + n])

    def program(self, addr: int, data: bytes) -> None:
        # Host simulation allows byte rewrite so two-phase header seals can set SEAL_PAY.
        self.mem[addr : addr + len(data)] = data

    def erase_page(self, page: int) -> None:
        base = page * PAGE_SIZE
        self.mem[base : base + PAGE_SIZE] = b"\xff" * PAGE_SIZE


@dataclass
class Record:
    flags: int
    key: bytes
    value: bytes
    seq: int
    complete: bool


def _hdr_bytes(flags: int, key_len: int, val_len: int, seq: int) -> bytes:
    body = bytes(
        [
            MAGIC & 0xFF,
            (MAGIC >> 8) & 0xFF,
            flags & 0xFF,
            key_len & 0xFF,
            val_len & 0xFF,
            (val_len >> 8) & 0xFF,
            seq & 0xFF,
            (seq >> 8) & 0xFF,
        ]
    )
    c = crc16_ccitt(body)
    return body + bytes([c & 0xFF, (c >> 8) & 0xFF])


class RingLog:
    def __init__(self, flash: Flash):
        self.flash = flash
        self.next_seq = 1
        self.write_page = 0
        self.write_off = 0
        self._rescan()

    def record_complete(
        self, page: int, offset: int, flags: int, key_len: int, val_len: int
    ) -> bool:
        if not (flags & SEAL_HDR) or not (flags & SEAL_PAY):
            return False
        pay_len = key_len + val_len
        addr = page * PAGE_SIZE + offset + HDR_SIZE
        payload = self.flash.read(addr, pay_len + 2)
        pay = payload[:pay_len]
        got = payload[pay_len] | (payload[pay_len + 1] << 8)
        return crc16_ccitt(pay) == got


    def _rescan(self) -> None:
        max_seq = None
        end_page, end_off = 0, 0
        saw = False
        for page in range(RING_PAGES):
            off = 0
            while off + HDR_SIZE <= PAGE_SIZE:
                raw = self.flash.read(page * PAGE_SIZE + off, HDR_SIZE)
                if raw[0] == 0xFF and raw[1] == 0xFF:
                    break
                magic = raw[0] | (raw[1] << 8)
                if magic != MAGIC:
                    off += 1
                    continue
                flags = raw[2]
                key_len = raw[3]
                val_len = raw[4] | (raw[5] << 8)
                seq = raw[6] | (raw[7] << 8)
                hdr_crc = raw[8] | (raw[9] << 8)
                if crc16_ccitt(raw[:8]) != hdr_crc:
                    off += 1
                    continue
                total = HDR_SIZE + key_len + val_len + 2
                if off + total > PAGE_SIZE:
                    break
                if self.record_complete(page, off, flags, key_len, val_len):
                    if max_seq is None or newer_seq(max_seq, seq):
                        max_seq = seq
                off += total
                end_page, end_off = page, off
                saw = True
        if not saw:
            self.write_page = 0
            self.write_off = 0
        else:
            self.write_page = end_page
            self.write_off = end_off
        if max_seq is None:
            self.next_seq = 1
        else:
            self.next_seq = (max_seq + 1) & 0xFFFF
            if self.next_seq == 0:
                self.next_seq = 1

    def iter_records(self) -> Iterator[Record]:
        for page in range(RING_PAGES):
            off = 0
            while off + HDR_SIZE <= PAGE_SIZE:
                raw = self.flash.read(page * PAGE_SIZE + off, HDR_SIZE)
                if raw[0] == 0xFF and raw[1] == 0xFF:
                    break
                magic = raw[0] | (raw[1] << 8)
                if magic != MAGIC:
                    off += 1
                    continue
                flags = raw[2]
                key_len = raw[3]
                val_len = raw[4] | (raw[5] << 8)
                seq = raw[6] | (raw[7] << 8)
                hdr_crc = raw[8] | (raw[9] << 8)
                if crc16_ccitt(raw[:8]) != hdr_crc:
                    off += 1
                    continue
                total = HDR_SIZE + key_len + val_len + 2
                if off + total > PAGE_SIZE:
                    break
                addr = page * PAGE_SIZE + off + HDR_SIZE
                payload = self.flash.read(addr, key_len + val_len)
                complete = self.record_complete(page, off, flags, key_len, val_len)
                yield Record(
                    flags=flags,
                    key=payload[:key_len],
                    value=payload[key_len : key_len + val_len],
                    seq=seq,
                    complete=complete,
                )
                off += total

    def ensure_space(self, need: int, reclaim_cb: Callable[[], None]) -> None:
        while True:
            if self.write_page >= RING_PAGES:
                reclaim_cb()
                keep_next = self.next_seq
                self._rescan()
                self.next_seq = keep_next
                if self.write_page >= RING_PAGES:
                    raise RuntimeError("ring log full after compact")
                continue
            if self.write_off + need <= PAGE_SIZE:
                return
            nxt = self.write_page + 1
            if nxt >= RING_PAGES:
                reclaim_cb()
                keep_next = self.next_seq
                self._rescan()
                self.next_seq = keep_next
                continue
            self.write_page = nxt
            self.write_off = 0

    def append(
        self,
        key: bytes,
        value: bytes,
        tombstone: bool = False,
        tear: Optional[str] = None,
        reclaim_cb: Optional[Callable[[], None]] = None,
    ) -> int:
        if reclaim_cb is None:
            reclaim_cb = lambda: None
        if tombstone:
            value = b""
        need = HDR_SIZE + len(key) + len(value) + 2
        self.ensure_space(need, reclaim_cb)
        seq = self.next_seq
        self.next_seq = (self.next_seq + 1) & 0xFFFF
        if self.next_seq == 0:
            self.next_seq = 1
        flags = SEAL_HDR
        if tombstone:
            flags |= TOMBSTONE
        hdr = _hdr_bytes(flags, len(key), len(value), seq)
        addr = self.write_page * PAGE_SIZE + self.write_off
        self.flash.program(addr, hdr)
        if tear == "after_header":
            self.write_off += need
            return seq
        pay = key + value
        pay_c = crc16_ccitt(pay)
        self.flash.program(
            addr + HDR_SIZE, pay + bytes([pay_c & 0xFF, (pay_c >> 8) & 0xFF])
        )
        if tear == "after_payload":
            self.write_off += need
            return seq
        sealed = _hdr_bytes(flags | SEAL_PAY, len(key), len(value), seq)
        self.flash.program(addr, sealed)
        self.write_off += need
        return seq

    def tip_seq(self) -> int:
        gen = None
        for rec in self.iter_records():
            if not rec.complete:
                continue
            if gen is None or newer_seq(gen, rec.seq):
                gen = rec.seq
        return 0 if gen is None else gen


def fold_live(ring: RingLog) -> Dict[bytes, Tuple[bytes, int]]:
    state: Dict[bytes, Tuple[Optional[bytes], int]] = {}
    for rec in ring.iter_records():
        if not rec.complete:
            continue
        prev = state.get(rec.key)
        if prev is not None and not newer_seq(prev[1], rec.seq):
            continue
        if rec.flags & TOMBSTONE:
            state[rec.key] = (None, rec.seq)
        else:
            state[rec.key] = (rec.value, rec.seq)
    live: Dict[bytes, Tuple[bytes, int]] = {}
    for k, (val, seq) in state.items():
        if val is None:
            continue
        live[k] = (val, seq)
    return live


def _live_order(a, b) -> int:
    sa = a[1][1]
    sb = b[1][1]
    if sa == sb:
        return 0
    if newer_seq(sa, sb):
        return -1
    if newer_seq(sb, sa):
        return 1
    return 0


def compact(flash: Flash, ring: RingLog) -> None:
    live = fold_live(ring)
    next_seq = ring.next_seq
    for page in range(RING_PAGES):
        flash.erase_page(page)
    ring.write_page = 0
    ring.write_off = 0
    ring.next_seq = next_seq
    items = sorted(live.items(), key=cmp_to_key(_live_order))
    for key, (value, _seq) in items:
        ring.append(key, value, tombstone=False, tear=None, reclaim_cb=lambda: None)


def recover_nvs(ring: RingLog) -> Dict[str, str]:
    state: Dict[bytes, tuple] = {}
    for rec in ring.iter_records():
        if not rec.complete:
            continue
        prev = state.get(rec.key)
        if prev is not None and not newer_seq(prev[0], rec.seq):
            continue
        if rec.flags & TOMBSTONE:
            state[rec.key] = (rec.seq, None)
        else:
            state[rec.key] = (rec.seq, rec.value)
    out: Dict[str, str] = {}
    for k, (_seq, val) in state.items():
        if val is None:
            continue
        out[k.decode("utf-8")] = val.decode("utf-8")
    return dict(sorted(out.items()))


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


def write_bank(flash: Flash, which: str, info: SlotInfo) -> None:
    page = BANK_X_PAGE if which == "X" else BANK_Y_PAGE
    flash.erase_page(page)
    flash.program(
        page * PAGE_SIZE,
        _pack_slot(
            info.state,
            info.slot_id,
            info.security_version,
            info.generation,
            info.image_version,
        ),
    )


def read_bank(flash: Flash, which: str) -> SlotInfo:
    page = BANK_X_PAGE if which == "X" else BANK_Y_PAGE
    raw = flash.read(page * PAGE_SIZE, 14)
    magic = raw[0] | (raw[1] << 8)
    if magic != MAGIC_SLOT:
        return BankInfo(EMPTY, BANK_ID[which], 0, 0, 0, False)
    state = raw[2]
    slot_id = raw[3]
    sec = raw[4] | (raw[5] << 8)
    gen = raw[6] | (raw[7] << 8)
    img = raw[8] | (raw[9] << 8) | (raw[10] << 16) | (raw[11] << 24)
    crc = raw[12] | (raw[13] << 8)
    ok = crc16_ccitt(raw[:12]) == crc
    return BankInfo(state, slot_id, sec, gen, img, ok)


def _pack_meta(floor: int, epoch: int, policy: int = 0) -> bytes:
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


def _program_meta_page(flash: Flash, page: int, floor: int, epoch: int, policy: int = 0) -> None:
    flash.erase_page(page)
    flash.program(page * PAGE_SIZE, _pack_meta(floor, epoch, policy))



REQUIRE_NEWER_SECURITY = 0x0001
IGNORE_ACTIVE_PREF = 0x0002


def _read_meta_full(flash: Flash):
    best = None
    for page in (META_PAGE, META_MIRROR_PAGE):
        parsed = _unpack_meta(flash.read(page * PAGE_SIZE, 10))
        if parsed is None:
            continue
        floor, epoch, policy = parsed
        if best is None or newer_seq(best[0], epoch):
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
        if max_epoch == 0 or newer_seq(max_epoch, epoch):
            max_epoch = epoch
    next_epoch = (max_epoch + 1) & 0xFFFF
    if next_epoch == 0:
        next_epoch = 1
    flash.erase_page(META_MIRROR_PAGE)
    flash.program(META_MIRROR_PAGE * PAGE_SIZE, _pack_meta(floor, next_epoch, policy & 0xFFFF))
    if tear == "after_mirror":
        return
    flash.erase_page(META_PAGE)
    flash.program(META_PAGE * PAGE_SIZE, _pack_meta(floor, next_epoch, policy & 0xFFFF))


def read_meta(flash: Flash) -> int:
    floor, _policy = _read_meta_full(flash)
    return floor


def select_boot_bank(flash: Flash):
    floor, policy = _read_meta_full(flash)
    pool = []
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
        if newer_seq(best.generation, info.generation):
            best_name, best = name, info
            continue
        if newer_seq(info.generation, best.generation):
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
    write_bank(
        flash,
        which,
        BankInfo(CANDIDATE, sid, security_version, generation, image_version, True),
    )
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


class Runtime:
    def __init__(self, sec_floor: int = 1):
        self.flash = Flash()
        write_meta(self.flash, sec_floor)
        self.ring = RingLog(self.flash)

    def _compact(self) -> None:
        compact(self.flash, self.ring)
        self.ring._rescan()

    def put(self, key: str, value: str, tear: Optional[str] = None) -> None:
        self.ring.append(
            key.encode("utf-8"),
            value.encode("utf-8"),
            tombstone=False,
            tear=tear,
            reclaim_cb=self._compact,
        )

    def delete(self, key: str, tear: Optional[str] = None) -> None:
        self.ring.append(
            key.encode("utf-8"),
            b"",
            tombstone=True,
            tear=tear,
            reclaim_cb=self._compact,
        )

    def force_meta_epoch(self, floor: int, epoch: int) -> None:
        epoch = epoch & 0xFFFF
        if epoch == 0:
            epoch = 1
        _cur_floor, policy = _read_meta_full(self.flash)
        for page in (META_PAGE, META_MIRROR_PAGE):
            _program_meta_page(
                self.flash,
                page,
                int(floor) & 0xFFFF,
                epoch,
                policy & 0xFFFF,
            )

    def apply_ops(self, ops: List[Dict[str, Any]]) -> None:
        for op in ops:
            kind = op["op"]
            if kind == "put":
                self.put(op["key"], op["value"], tear=op.get("tear"))
            elif kind == "delete":
                self.delete(op["key"], tear=op.get("tear"))
            elif kind == "promote":
                tip = self.ring.tip_seq()
                promote(
                    self.flash,
                    op["bank"],
                    int(op["sec_rev"]),
                    int(op["image_version"]),
                    generation=tip,
                    tear=op.get("tear"),
                )
            elif kind == "force_meta_epoch":
                self.force_meta_epoch(int(op["floor"]), int(op["epoch"]))
            elif kind == "force_seq":
                self.ring.next_seq = int(op["seq"]) & 0xFFFF
                if self.ring.next_seq == 0:
                    self.ring.next_seq = 1
            elif kind == "pad_puts":
                count = int(op.get("count", 40))
                val_len = int(op.get("val_len", 40))
                for i in range(count):
                    self.put(f"pad{i % 8}", (f"{i:04d}" + "x" * val_len)[:val_len])
            elif kind == "set_policy":
                write_meta(self.flash, read_meta(self.flash), policy=int(op["policy"]), tear=op.get("tear"))
            elif kind == "raise_floor":
                write_meta(self.flash, int(op["floor"]), tear=op.get("tear"))
            elif kind == "reboot":
                self.ring = RingLog(self.flash)
            else:
                raise ValueError(kind)

    def recover(self, case_id: str) -> Dict[str, Any]:
        ring = RingLog(self.flash)
        nvs = recover_nvs(ring)
        boot, sec, floor = select_boot_bank(self.flash)
        return {
            "case_id": case_id,
            "nvs": nvs,
            "boot_bank": boot,
            "sec_rev": sec,
            "tip_seq": ring.tip_seq(),
            "sec_floor": floor,
        }


def run_case(script: Dict[str, Any]) -> Dict[str, Any]:
    rt = Runtime(sec_floor=int(script.get("sec_floor", 1)))
    rt.apply_ops(script.get("ops", []))
    return rt.recover(script["case_id"])


def expected_for_cases(cases_dir: Path) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for p in sorted(cases_dir.glob("*/script.json")):
        script = json.loads(p.read_text(encoding="utf-8"))
        out[script["case_id"]] = run_case(script)
    return out
