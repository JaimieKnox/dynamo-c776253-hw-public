"""Case orchestration: apply case scripts and emit state JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .flash_hal import META_MIRROR_PAGE, META_PAGE, PAGE_SIZE, Flash
from .ringlog import RingLog
from .nvs import recover_nvs
from .compact import compact
from .banks import (
    _pack_meta,
    promote,
    read_meta,
    select_boot_bank,
    write_meta,
)


class Runtime:
    def __init__(self, sec_floor: int = 1):
        self.flash = Flash()
        write_meta(self.flash, sec_floor)
        self.ring = RingLog(self.flash)

    def _compact(self) -> None:
        keep = self.ring.next_seq
        compact(self.flash, self.ring)
        self.ring._rescan()
        self.ring.next_seq = keep

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

    def pad_puts(self, count: int, val_len: int = 40) -> None:
        for i in range(count):
            k = f"pad{i % 8}"
            v = (f"{i:04d}" + "x" * val_len)[:val_len]
            self.put(k, v)

    def do_promote(
        self,
        bank: str,
        sec_rev: int,
        image_version: int,
        tear: Optional[str] = None,
    ) -> None:
        stamp = 0
        for rec in self.ring.iter_records():
            if rec.complete:
                stamp = rec.seq
        promote(
            self.flash,
            bank,
            sec_rev,
            image_version,
            generation=stamp,
            tear=tear,
        )

    def force_meta_epoch(self, floor: int, epoch: int) -> None:
        epoch = epoch & 0xFFFF
        if epoch == 0:
            epoch = 1
        from .banks import _read_meta_full

        _floor, policy = _read_meta_full(self.flash)
        payload = _pack_meta(int(floor) & 0xFFFF, epoch, policy & 0xFFFF)
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
                    op["bank"],
                    int(op["sec_rev"]),
                    int(op["image_version"]),
                    tear=op.get("tear"),
                )
            elif kind == "force_meta_epoch":
                self.force_meta_epoch(int(op["floor"]), int(op["epoch"]))
            elif kind == "force_seq":
                self.ring.next_seq = int(op["seq"]) & 0xFFFF
                if self.ring.next_seq == 0:
                    self.ring.next_seq = 1
            elif kind == "pad_puts":
                self.pad_puts(int(op.get("count", 40)), int(op.get("val_len", 40)))
            elif kind == "raise_floor":
                self.raise_floor(int(op["floor"]), tear=op.get("tear"))
            elif kind == "set_policy":
                self.set_policy(int(op["policy"]), tear=op.get("tear"))
            elif kind == "reboot":
                self.ring = RingLog(self.flash)
            else:
                raise ValueError(f"unknown op {kind}")

    def recover(self, case_id: str) -> Dict[str, Any]:
        ring = RingLog(self.flash)
        nvs = recover_nvs(ring)
        boot, sec, floor = select_boot_bank(self.flash)
        tip = ring.tip_seq()
        return {
            "case_id": case_id,
            "nvs": nvs,
            "boot_bank": boot,
            "sec_rev": sec,
            "tip_seq": tip,
            "sec_floor": floor,
        }


def run_case(script: Dict[str, Any]) -> Dict[str, Any]:
    floor = int(script.get("sec_floor", 1))
    rt = Runtime(sec_floor=floor)
    rt.apply_ops(script.get("ops", []))
    return rt.recover(script["case_id"])


def run_cases_dir(cases_dir: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    scripts = []
    for p in sorted(cases_dir.glob("*/script.json")):
        scripts.append(json.loads(p.read_text(encoding="utf-8")))
    scripts.sort(key=lambda s: s["case_id"])
    report_path = out_dir / "suite_ledger.jsonl"
    with report_path.open("w", encoding="utf-8") as rep:
        for script in scripts:
            result = run_case(script)
            case_out = out_dir / script["case_id"]
            case_out.mkdir(parents=True, exist_ok=True)
            (case_out / "state.json").write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            rep.write(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")
