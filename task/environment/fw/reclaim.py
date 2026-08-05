"""Journal reclaim / compaction."""

from __future__ import annotations

from functools import cmp_to_key
from typing import Dict, Tuple

from .flash_hal import JOURNAL_PAGES, Flash
from .journal import TOMBSTONE, Journal, newer_seq


def fold_live(journal: Journal) -> Dict[bytes, Tuple[bytes, int]]:
    """Fold complete records into live key map for migration."""
    live: Dict[bytes, Tuple[bytes, int]] = {}
    for rec in journal.iter_records():
        if not rec.complete:
            continue
        if rec.flags & TOMBSTONE:
            continue
        prev = live.get(rec.key)
        if prev is None or newer_seq(prev[1], rec.seq):
            live[rec.key] = (rec.value, rec.seq)
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


def reclaim(flash: Flash, journal: Journal) -> None:
    """Compact journal: erase all journal pages and rewrite live records."""
    live = fold_live(journal)
    next_seq = journal.next_seq
    for page in range(JOURNAL_PAGES):
        flash.erase_page(page)
    journal.write_page = 0
    journal.write_off = 0
    journal.next_seq = next_seq
    items = sorted(live.items(), key=cmp_to_key(_live_order))
    for key, (value, _seq) in items:
        journal.append(key, value, tombstone=False, tear=None, reclaim_cb=lambda: None)
