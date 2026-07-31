"""Journal reclaim / compaction."""

from __future__ import annotations

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


def reclaim(flash: Flash, journal: Journal) -> None:
    """Compact journal: erase all journal pages and rewrite live records."""
    live = fold_live(journal)
    # preserve next_seq across reclaim
    next_seq = journal.next_seq
    for page in range(JOURNAL_PAGES):
        flash.erase_page(page)
    journal.write_page = 0
    journal.write_off = 0
    # Rewrite live keys then restore the preserved next_seq cursor.
    items = sorted(live.items(), key=lambda kv: kv[1][1])
    for key, (value, seq) in items:
        journal.next_seq = seq
        journal.append(key, value, tombstone=False, tear=None, reclaim_cb=lambda: None)
    journal.next_seq = next_seq
