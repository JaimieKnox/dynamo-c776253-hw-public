"""Ring log compaction."""

from __future__ import annotations

from functools import cmp_to_key
from typing import Dict, Optional, Tuple

from .flash_hal import RING_PAGES, Flash
from .ringlog import TOMBSTONE, RingLog, newer_seq


def fold_live(ring: RingLog) -> Dict[bytes, Tuple[bytes, int]]:
    """Fold complete records. Tombstone wins then key is omitted."""
    state: Dict[bytes, Tuple[Optional[bytes], int]] = {}
    for rec in ring.iter_records():
        if not rec.complete:
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
    """Compact ring: erase ring pages and rewrite live records."""
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
