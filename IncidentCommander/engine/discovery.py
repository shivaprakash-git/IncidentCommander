"""Full-file keyword scan -> candidate REAL incident windows.

Independent of whatever slice the parser ingested: it walks every record of the
export (segmentation only, no Event building), looks for the incident keywords,
skips known boilerplate (NOISE_RE) and anything inside non-record system blocks
(halt/load banner etc.), then turns each hit into a +/-15 min window and merges
overlapping windows (capped at MAX_WINDOW so one chatty day is not one incident).

CLI:  python -m engine.discovery [--save]
"""
from __future__ import annotations

import argparse
import re
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from . import db
from .config import DATA_FILE, DB_PATH
from .models import Candidate, Hit
from .parser import _iter_records
from .patterns import NOISE_RE

MARGIN = timedelta(minutes=15)
MAX_WINDOW = timedelta(minutes=60)
MAX_DEMO = 3

# keyword -> ranking weight (spec keyword list, most specific first)
KEYWORDS = {
    "SECURITY VIOLATION": 10, "HALT": 9, "ABEND": 9, "UNAUTHORIZED": 8, "VIOLATION": 6,
    "INVALID": 5, "FAILED": 4, "DISCARD": 3,
}
_KW_RE = {k: re.compile(r"\b" + re.escape(k), re.IGNORECASE) for k in KEYWORDS}

AUTH_KW = {"SECURITY VIOLATION", "VIOLATION", "INVALID", "UNAUTHORIZED"}


@dataclass
class DiscoveryResult:
    hits: list
    candidates: list
    keyword_counts: dict
    records_scanned: int


def _scan_record(text_lines: list) -> Optional[tuple]:
    kws, first = set(), None
    for ln in text_lines:
        if NOISE_RE.search(ln):
            continue
        for k, rx in _KW_RE.items():
            if rx.search(ln):
                kws.add(k)
                first = first or ln.strip()
    return (kws, first) if kws else None


def _classify(hits: list) -> str:
    primary = max(hits, key=lambda h: (KEYWORDS[h.keyword], -h.timestamp.timestamp()))
    if primary.keyword in AUTH_KW:
        return "auth_failure_security_violation"
    if primary.keyword == "HALT":
        return "halt_load"
    if primary.keyword == "ABEND":
        return "task_abend"
    if primary.keyword == "DISCARD":
        return "sumlog_discard"
    if any("LINKAGE FAILED" in h.text.upper() for h in hits):
        return "linkage_failure"
    return "operation_failed"


def _score(c: Candidate) -> int:
    return max(KEYWORDS[h.keyword] for h in c.hits) * 10 + min(len(c.hits), 10)


def discover(path=DATA_FILE) -> DiscoveryResult:
    hits: list = []
    n = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for rec in _iter_records(f):
            n += 1
            found = _scan_record([rec.body] + rec.cont)
            if found:
                kws, first = found
                primary = max(kws, key=lambda k: KEYWORDS[k])
                hits.append(Hit(rec.line_no, primary, sorted(kws), rec.ts, first))
    counts = Counter(k for h in hits for k in h.keywords)

    hits.sort(key=lambda h: h.timestamp)
    groups: list = []
    for h in hits:
        start, end = h.timestamp - MARGIN, h.timestamp + MARGIN
        if groups and start <= groups[-1]["end"] and end - groups[-1]["start"] <= MAX_WINDOW:
            groups[-1]["end"] = max(groups[-1]["end"], end)
            groups[-1]["hits"].append(h)
        else:
            groups.append({"start": start, "end": end, "hits": [h]})

    cands = []
    for i, g in enumerate(groups, 1):
        top = max(KEYWORDS[h.keyword] for h in g["hits"])
        trig = next(h for h in g["hits"] if KEYWORDS[h.keyword] == top)   # earliest hit of the worst class
        c = Candidate(
            incident_id=f"INC-R{i:02d}", source="real", type=_classify(g["hits"]),
            trigger_ts=trig.timestamp, window_start=g["start"], window_end=g["end"],
            hits=g["hits"], trigger_event_id=f"L{trig.line_no:06d}",
            description=f"{len(g['hits'])} keyword hit(s); first: {trig.text[:80]}",
        )
        cands.append(c)
    _mark_demo(cands)
    return DiscoveryResult(hits, cands, dict(counts), n)


def _mark_demo(cands: list) -> None:
    """Up to MAX_DEMO demo incidents: best score, preferring distinct types."""
    ranked = sorted(cands, key=_score, reverse=True)
    chosen, seen = [], set()
    for c in ranked:
        if c.type not in seen and len(chosen) < MAX_DEMO:
            chosen.append(c); seen.add(c.type)
    for c in ranked:
        if c not in chosen and len(chosen) < MAX_DEMO:
            chosen.append(c)
    for c in chosen:
        c.demo = True


def print_report(r: DiscoveryResult) -> None:
    print(f"records scanned: {r.records_scanned}   keyword hit records: {len(r.hits)}")
    print(f"keyword counts (after noise filter): {r.keyword_counts}")
    print(f"candidate incident windows: {len(r.candidates)}")
    for c in r.candidates:
        flag = "DEMO" if c.demo else "    "
        print(f" {flag} {c.incident_id} {c.type:<32} trigger {c.trigger_ts:%m-%d %H:%M:%S} "
              f"line {c.trigger_event_id}  window {c.window_start:%H:%M}-{c.window_end:%H:%M}  "
              f"hits={len(c.hits)} {c.keywords}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Full-file incident discovery scan")
    p.add_argument("--file", default=str(DATA_FILE))
    p.add_argument("--db", default=str(DB_PATH))
    p.add_argument("--save", action="store_true", help="write candidates to the incidents table")
    a = p.parse_args(argv)
    r = discover(a.file)
    print_report(r)
    print(f"real demo incidents: {sum(c.demo for c in r.candidates)} (synthetic fallback needed: "
          f"{'YES' if len(r.candidates) < MAX_DEMO else 'no'})")
    if a.save:
        db.save_incidents(db.connect(a.db), r.candidates)
        print("saved to incidents table")


if __name__ == "__main__":
    main()
