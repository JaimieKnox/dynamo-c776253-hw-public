"""Independent correct recovery model. Does not import /app/fw."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

PAGE_SIZE = 256
NUM_PAGES = 32
JOURNAL_PAGES = 28
SLOT_A_PAGE = 28
SLOT_B_PAGE = 29
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
SLOT_ID = {"A": 0, "B": 1}


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


class Journal:
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
        for page in range(JOURNAL_PAGES):
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
        for page in range(JOURNAL_PAGES):
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
            if self.write_page >= JOURNAL_PAGES:
                reclaim_cb()
                self._rescan()
                if self.write_page >= JOURNAL_PAGES:
                    raise RuntimeError("journal full after reclaim")
                continue
            if self.write_off + need <= PAGE_SIZE:
                return
            nxt = self.write_page + 1
            if nxt >= JOURNAL_PAGES:
                reclaim_cb()
                self._rescan()
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

    def max_generation(self) -> int:
        gen = None
        for rec in self.iter_records():
            if not rec.complete:
                continue
            if gen is None or newer_seq(gen, rec.seq):
                gen = rec.seq
        return 0 if gen is None else gen


def fold_live(journal: Journal) -> Dict[bytes, Tuple[bytes, int]]:
    state: Dict[bytes, Tuple[Optional[bytes], int]] = {}
    for rec in journal.iter_records():
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


def reclaim(flash: Flash, journal: Journal) -> None:
    live = fold_live(journal)
    next_seq = journal.next_seq
    for page in range(JOURNAL_PAGES):
        flash.erase_page(page)
    journal.write_page = 0
    journal.write_off = 0
    journal.next_seq = next_seq
    items = sorted(live.items(), key=lambda kv: kv[1][1])
    for key, (value, _seq) in items:
        journal.append(key, value, tombstone=False, tear=None, reclaim_cb=lambda: None)


def recover_kv(journal: Journal) -> Dict[str, str]:
    state: Dict[bytes, tuple] = {}
    for rec in journal.iter_records():
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
        if max_epoch == 0 or newer_seq(max_epoch, epoch):
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
        if best_epoch is None or newer_seq(best_epoch, epoch):
            best_epoch = epoch
            best_floor = floor
    return 0 if best_floor is None else best_floor


def select_boot_slot(flash: Flash) -> Tuple[Optional[str], Optional[int], int]:
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
    other = "B" if which == "A" else "A"
    sid = SLOT_ID[which]
    write_slot(
        flash,
        which,
        SlotInfo(CANDIDATE, sid, security_version, generation, image_version, True),
    )
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


class Device:
    def __init__(self, anti_rollback_min: int = 1):
        self.flash = Flash()
        write_meta(self.flash, anti_rollback_min)
        self.journal = Journal(self.flash)

    def _reclaim(self) -> None:
        reclaim(self.flash, self.journal)
        self.journal._rescan()

    def put(self, key: str, value: str, tear: Optional[str] = None) -> None:
        self.journal.append(
            key.encode("utf-8"),
            value.encode("utf-8"),
            tombstone=False,
            tear=tear,
            reclaim_cb=self._reclaim,
        )

    def delete(self, key: str, tear: Optional[str] = None) -> None:
        self.journal.append(
            key.encode("utf-8"),
            b"",
            tombstone=True,
            tear=tear,
            reclaim_cb=self._reclaim,
        )

    def force_meta_epoch(self, floor: int, epoch: int) -> None:
        epoch = epoch & 0xFFFF
        if epoch == 0:
            epoch = 1
        for page in (META_PAGE, META_MIRROR_PAGE):
            _program_meta_page(self.flash, page, int(floor) & 0xFFFF, epoch)

    def apply_ops(self, ops: List[Dict[str, Any]]) -> None:
        for op in ops:
            kind = op["op"]
            if kind == "put":
                self.put(op["key"], op["value"], tear=op.get("tear"))
            elif kind == "delete":
                self.delete(op["key"], tear=op.get("tear"))
            elif kind == "promote":
                gen = self.journal.max_generation()
                promote(
                    self.flash,
                    op["slot"],
                    int(op["security_version"]),
                    int(op["image_version"]),
                    generation=gen,
                    tear=op.get("tear"),
                )
            elif kind == "force_meta_epoch":
                self.force_meta_epoch(int(op["floor"]), int(op["epoch"]))
            elif kind == "force_seq":
                self.journal.next_seq = int(op["seq"]) & 0xFFFF
                if self.journal.next_seq == 0:
                    self.journal.next_seq = 1
            elif kind == "pad_puts":
                count = int(op.get("count", 40))
                val_len = int(op.get("val_len", 40))
                for i in range(count):
                    self.put(f"pad{i % 8}", (f"{i:04d}" + "x" * val_len)[:val_len])
            elif kind == "raise_floor":
                write_meta(self.flash, int(op["floor"]), tear=op.get("tear"))
            else:
                raise ValueError(kind)

    def recover(self, job_id: str) -> Dict[str, Any]:
        j = Journal(self.flash)
        kv = recover_kv(j)
        boot, sec, floor = select_boot_slot(self.flash)
        return {
            "job_id": job_id,
            "kv": kv,
            "boot_slot": boot,
            "security_version": sec,
            "generation": j.max_generation(),
            "anti_rollback_min": floor,
        }


def run_job(script: Dict[str, Any]) -> Dict[str, Any]:
    dev = Device(anti_rollback_min=int(script.get("anti_rollback_min", 1)))
    dev.apply_ops(script.get("ops", []))
    return dev.recover(script["job_id"])


def expected_for_jobs(jobs_dir: Path) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for p in sorted(jobs_dir.glob("*/script.json")):
        script = json.loads(p.read_text(encoding="utf-8"))
        out[script["job_id"]] = run_job(script)
    return out
