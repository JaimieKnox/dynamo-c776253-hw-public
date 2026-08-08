"""NOR ring log with two-phase sealed records (corrected)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterator, Optional

from .crc16 import crc16_ccitt
from .flash_hal import RING_PAGES, PAGE_SIZE, Flash

MAGIC = 0xA55A
HDR_SIZE = 10
TOMBSTONE = 0x01
SEAL_HDR = 0x02
SEAL_PAY = 0x04


@dataclass
class Record:
    page: int
    offset: int
    flags: int
    key: bytes
    value: bytes
    seq: int
    complete: bool


def newer_seq(a: int, b: int) -> bool:
    """Return True if sequence b is strictly newer than a (16-bit modular)."""
    delta = (b - a) & 0xFFFF
    return 1 <= delta <= 32767


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

    def record_complete(
        self, page: int, offset: int, flags: int, key_len: int, val_len: int
    ) -> bool:
        """Require SEAL_HDR, SEAL_PAY, and matching pay_crc."""
        if not (flags & SEAL_HDR) or not (flags & SEAL_PAY):
            return False
        pay_len = key_len + val_len
        addr = page * PAGE_SIZE + offset + HDR_SIZE
        payload = self.flash.read(addr, pay_len + 2)
        pay = payload[:pay_len]
        got = payload[pay_len] | (payload[pay_len + 1] << 8)
        return crc16_ccitt(pay) == got

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
                    page=page,
                    offset=off,
                    flags=flags,
                    key=payload[:key_len],
                    value=payload[key_len : key_len + val_len],
                    seq=seq,
                    complete=complete,
                )
                off += total

    def space_needed(self, key: bytes, value: bytes) -> int:
        return HDR_SIZE + len(key) + len(value) + 2

    def ensure_space(self, need: int, reclaim_cb: Callable[[], None]) -> None:
        while True:
            if self.write_page >= RING_PAGES:
                reclaim_cb()
                self._rescan()
                if self.write_page >= RING_PAGES:
                    raise RuntimeError("ring log full after compact")
                continue
            if self.write_off + need <= PAGE_SIZE:
                return
            nxt = self.write_page + 1
            if nxt >= RING_PAGES:
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
        need = self.space_needed(key, value)
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
