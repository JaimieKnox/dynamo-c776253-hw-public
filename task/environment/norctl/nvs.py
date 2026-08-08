"""NVS recovery fold that respects tombstones."""

from __future__ import annotations

from typing import Dict

from .ringlog import TOMBSTONE, RingLog


def recover_nvs(ring: RingLog) -> Dict[str, str]:
    """Fold complete records. Tombstones win then omit the key."""
    state: Dict[bytes, tuple] = {}
    for rec in ring.iter_records():
        if not rec.complete:
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
