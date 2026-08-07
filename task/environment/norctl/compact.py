"""Ring log compaction."""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from .flash_hal import RING_PAGES, Flash
from .ringlog import TOMBSTONE, RingLog, newer_seq


def fold_live(ring: RingLog) -> Dict[bytes, Tuple[bytes, int]]:
    """Fold complete records. Tombstone wins then key is omitted."""
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


def compact(flash: Flash, ring: RingLog) -> None:
    """Compact ring: erase ring pages and rewrite live records."""
    live = fold_live(ring)
    next_seq = ring.next_seq
    for page in range(RING_PAGES):
        flash.erase_page(page)
    ring.write_page = 0
    ring.write_off = 0
    ring.next_seq = next_seq
    items = sorted(live.items(), key=lambda kv: kv[0])
    for key, (value, _seq) in items:
        ring.append(key, value, tombstone=False, tear=None, reclaim_cb=lambda: None)
    ring.next_seq = next_seq
