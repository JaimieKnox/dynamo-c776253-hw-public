"""Device orchestration: apply job scripts and emit recovered JSON ."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .flash_hal import Flash
from .journal import Journal
from .kv import recover_kv
from .reclaim import reclaim
from .flash_hal import META_MIRROR_PAGE, META_PAGE, PAGE_SIZE
from .slots import (
    _pack_meta,
    promote,
    read_meta,
    select_boot_slot,
    write_meta,
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

    def pad_puts(self, count: int, val_len: int = 40) -> None:
        # Reuse a small key set so reclaim can discard obsolete versions.
        for i in range(count):
            k = f"pad{i % 8}"
            v = (f"{i:04d}" + "x" * val_len)[:val_len]
            self.put(k, v)

    def do_promote(
        self,
        slot: str,
        security_version: int,
        image_version: int,
        tear: Optional[str] = None,
    ) -> None:
        gen = 0
        for rec in self.journal.iter_records():
            if rec.complete:
                gen = rec.seq
        promote(
            self.flash,
            slot,
            security_version,
            image_version,
            generation=gen,
            tear=tear,
        )

    def force_meta_epoch(self, floor: int, epoch: int) -> None:
        epoch = epoch & 0xFFFF
        if epoch == 0:
            epoch = 1
        payload = _pack_meta(int(floor) & 0xFFFF, epoch, 0)
        for page in (META_PAGE, META_MIRROR_PAGE):
            self.flash.erase_page(page)
            self.flash.program(page * PAGE_SIZE, payload)
    def raise_floor(self, floor: int, tear: Optional[str] = None) -> None:
        write_meta(self.flash, floor, tear=tear)

    def set_policy(self, policy: int, tear: Optional[str] = None) -> None:
        write_meta(self.flash, read_meta(self.flash), policy=int(policy), tear=tear)

    def apply_ops(self, ops: List[Dict[str, Any]]) -> None:
        for op in ops:
            kind = op["op"]
            if kind == "put":
                self.put(op["key"], op["value"], tear=op.get("tear"))
            elif kind == "delete":
                self.delete(op["key"], tear=op.get("tear"))
            elif kind == "promote":
                self.do_promote(
                    op["slot"],
                    int(op["security_version"]),
                    int(op["image_version"]),
                    tear=op.get("tear"),
                )
            elif kind == "force_meta_epoch":
                self.force_meta_epoch(int(op["floor"]), int(op["epoch"]))
            elif kind == "force_seq":
                self.journal.next_seq = int(op["seq"]) & 0xFFFF
                if self.journal.next_seq == 0:
                    self.journal.next_seq = 1
            elif kind == "pad_puts":
                self.pad_puts(int(op.get("count", 40)), int(op.get("val_len", 40)))
            elif kind == "raise_floor":
                self.raise_floor(int(op["floor"]), tear=op.get("tear"))
            elif kind == "set_policy":
                self.set_policy(int(op["policy"]), tear=op.get("tear"))
            elif kind == "reboot":
                self.journal = Journal(self.flash)
            else:
                raise ValueError(f"unknown op {kind}")

    def recover(self, job_id: str) -> Dict[str, Any]:
        # fresh Journal view over same flash
        j = Journal(self.flash)
        kv = recover_kv(j)
        boot, sec, floor = select_boot_slot(self.flash)
        gen = j.max_generation()
        return {
            "job_id": job_id,
            "kv": kv,
            "boot_slot": boot,
            "security_version": sec,
            "generation": gen,
            "anti_rollback_min": floor if floor else read_meta(self.flash),
        }

def run_job(script: Dict[str, Any]) -> Dict[str, Any]:
    floor = int(script.get("anti_rollback_min", 1))
    dev = Device(anti_rollback_min=floor)
    dev.apply_ops(script.get("ops", []))
    return dev.recover(script["job_id"])

def run_jobs_dir(jobs_dir: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    scripts = []
    for p in sorted(jobs_dir.glob("*/script.json")):
        scripts.append(json.loads(p.read_text(encoding="utf-8")))
    scripts.sort(key=lambda s: s["job_id"])
    report_path = out_dir / "batch_report.jsonl"
    with report_path.open("w", encoding="utf-8") as rep:
        for script in scripts:
            result = run_job(script)
            job_out = out_dir / script["job_id"]
            job_out.mkdir(parents=True, exist_ok=True)
            (job_out / "recovered.json").write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            rep.write(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")
