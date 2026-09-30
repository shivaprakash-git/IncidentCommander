"""Segmentation parser for LOGANALYZER text exports of MCP SUMLOG.

A record = one HEADER line (timestamp [KEYWORD] <mix number> text) plus the
indented continuation lines that follow it. Two header shapes exist in real
files: the 3-space-indented `HH:MM:SS` style and the unindented fractional
`HH:MM:SS.ffff` TIME/DIAG style. Dates come from the day lines
("Thursday, August 10, 2023"). Unindented / lightly-indented text that is not a
header (e.g. the "GENERAL MCP INFORMATION" halt/load block) is a *system
block*: it is never glued onto the previous record.

CLI:  python -m engine.parser --max-records 500 --show 10
"""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Iterator, Optional

from . import db
from .config import DATA_FILE, DB_PATH
from .models import Event
from .patterns import BODY_RE, CRIT_RE, DATED_HEADER_RE, DAY_RE, FILE_RECORDS_RE, HEADER_RE, NOISE_RE, WARN_RE

DEFAULT_MAX_RECORDS = 5000
CONT_MIN_INDENT = 4          # continuation lines are indented >= this; less => system block

# Issue #4 mapping table. BOJ/EOJ/LOGON/LGOFF come from the reference doc's
# Log Entry Classes table. Anything else -> UNMAPPED/<raw keyword>.
MAPPING = {
    "BOJ": ("1", "1"), "EOJ": ("1", "2"), "BOT": ("1", "3"), "EOT": ("1", "4"),
    "OPEN": ("1", "5"), "CLOSE": ("1", "6"),
    "LOGON": ("4", "1"), "LGOFF": ("4", "2"),
    "EI": ("JOB", "TASK_INFO"), "TIME": ("SYSTEM", "TIME_MSG"),
    "INFO": ("INFO", "GENERIC"),          # header with no type keyword
}

_MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], 1)}
_LABEL = re.compile(r"^([A-Z][A-Z0-9 /#_.()-]{0,38}?)\s*:\s*(.*)$")
_EQ = re.compile(r"^([A-Z][A-Z0-9 /#_.-]{0,38}?)\s*=\s*(.*)$")
_JOB_IN_TEXT = re.compile(r"\bJOB (\d+)")


@dataclass
class SliceSpec:
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    max_records: Optional[int] = None

    def effective_max(self) -> Optional[int]:
        """Bounded by default; an explicit line/time range is left uncapped."""
        if self.max_records is not None:
            return self.max_records
        if any(v is not None for v in (self.start_line, self.end_line, self.start_time, self.end_time)):
            return None
        return DEFAULT_MAX_RECORDS


def map_type(keyword: str) -> tuple:
    return MAPPING.get(keyword, ("UNMAPPED", keyword))


def parse_fields(line: str) -> dict:
    """Best-effort LABEL: value / LABEL = value extraction from one line."""
    out: dict = {}
    for seg in re.split(r"\s{2,}", line.strip()):
        m = _LABEL.match(seg)
        if m:
            out.setdefault(m.group(1).strip(), m.group(2).strip().rstrip("."))
            continue
        for part in seg.split(", "):
            m = _EQ.match(part.strip())
            if m:
                out.setdefault(m.group(1).strip(), m.group(2).strip().rstrip("."))
    return out


def severity_of(text: str) -> str:
    text = NOISE_RE.sub(" ", text)
    if CRIT_RE.search(text):
        return "CRIT"
    if WARN_RE.search(text):
        return "WARN"
    return "INFO"


@dataclass
class _Rec:
    line_no: int
    ts: datetime
    body: str
    cont: list


def _iter_records(lines: Iterable[str]) -> Iterator[_Rec]:
    date = None
    cur: Optional[_Rec] = None
    in_block = True
    for line_no, raw in enumerate(lines, 1):
        line = raw.rstrip()
        m = DAY_RE.match(line)
        if m:
            if cur:
                yield cur
                cur = None
            date = datetime(int(m.group(3)), _MONTHS[m.group(1)], int(m.group(2)))
            in_block = True
            continue
        m = DATED_HEADER_RE.match(line)
        if m:
            if cur:
                yield cur
            frac = m.group(7)
            ts = datetime(int(m.group(3)), int(m.group(1)), int(m.group(2)), int(m.group(4)),
                          int(m.group(5)), int(m.group(6)), int(frac.ljust(6, "0")[:6]) if frac else 0)
            cur = _Rec(line_no, ts, m.group(8).strip(), [])
            in_block = False
            continue
        m = HEADER_RE.match(line)
        if m and date is not None:
            if cur:
                yield cur
            frac = m.group(4)
            micro = int(frac.ljust(6, "0")[:6]) if frac else 0
            ts = date.replace(hour=int(m.group(1)), minute=int(m.group(2)),
                              second=int(m.group(3)), microsecond=micro)
            cur = _Rec(line_no, ts, m.group(5).strip(), [])
            in_block = False
            continue
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if cur is not None and not in_block and indent >= CONT_MIN_INDENT:
            cur.cont.append(line.strip())
        else:                       # system block / preamble / footer: not a record
            if cur:
                yield cur
                cur = None
            in_block = True
    if cur:
        yield cur


def _build_event(rec: _Rec, source: str, id_prefix: str) -> Event:
    m = BODY_RE.match(rec.body)
    if m:
        kw, num, text = m.group("kw") or "INFO", m.group("num"), m.group("text") or ""
    else:
        kw, num, text = "INFO", None, rec.body
    fields = parse_fields(text)
    for c in rec.cont:
        for k, v in parse_fields(c).items():
            fields.setdefault(k, v)
    raw_text = "\n".join([rec.body] + rec.cont)

    jn = re.match(r"\d+", fields.get("JOB NUMBER", ""))   # value can run into the next label
    job = jn.group(0) if jn else None
    if not job:
        jm = _JOB_IN_TEXT.search(raw_text)
        job = jm.group(1) if jm else num
    session = None
    for mcs, lsn in (("MCS NUMBER", "LSN NUMBER"), ("ORIGINATING MCS", "ORIGINATING LSN")):
        if fields.get(mcs) and fields.get(lsn):
            session = f"MCS{fields[mcs]}/LSN{fields[lsn]}"
            break
    if not session:
        session = fields.get("STATION NAME") or fields.get("STATIONNAME") or None

    major, minor = map_type(kw)
    return Event(
        event_id=f"{id_prefix}{rec.line_no:06d}", timestamp=rec.ts, job_id=job, task_id=num,
        session_id=session, major_type=major, minor_type=minor, raw_type_keyword=kw,
        raw_fields=fields, severity=severity_of(raw_text), raw_text=raw_text,
        source=source, line_no=rec.line_no,
    )


def parse_lines(lines: Iterable[str], spec: Optional[SliceSpec] = None,
                source: str = "real", id_prefix: str = "L") -> list:
    spec = spec or SliceSpec()
    cap = spec.effective_max()
    out: list = []
    for rec in _iter_records(lines):
        if spec.end_line is not None and rec.line_no > spec.end_line:
            break
        if spec.start_line is not None and rec.line_no < spec.start_line:
            continue
        if spec.start_time and rec.ts < spec.start_time:
            continue
        if spec.end_time and rec.ts > spec.end_time:
            continue
        out.append(_build_event(rec, source, id_prefix))
        if cap is not None and len(out) >= cap:
            break
    return out


def parse_file(path=DATA_FILE, spec: Optional[SliceSpec] = None) -> list:
    with open(path, encoding="utf-8", errors="replace") as f:
        return parse_lines(f, spec)


def count_records(path=DATA_FILE) -> tuple:
    """(header-delimited record count over the whole file, count LOGANALYZER reports)."""
    reported = None
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = list(f)
    for ln in lines[:40]:
        m = FILE_RECORDS_RE.search(ln)
        if m:
            reported = int(m.group(1))
            break
    return sum(1 for _ in _iter_records(lines)), reported


def summarize(events: list) -> dict:
    by_major: dict = {}
    by_sev: dict = {}
    unmapped_kw: dict = {}
    for e in events:
        by_major[e.major_type] = by_major.get(e.major_type, 0) + 1
        by_sev[e.severity] = by_sev.get(e.severity, 0) + 1
        if e.major_type == "UNMAPPED":
            unmapped_kw[e.minor_type] = unmapped_kw.get(e.minor_type, 0) + 1
    total = len(events)
    return {
        "total": total,
        "by_major": dict(sorted(by_major.items(), key=lambda kv: -kv[1])),
        "by_severity": by_sev,
        "unmapped_pct": round(100.0 * by_major.get("UNMAPPED", 0) / total, 1) if total else 0.0,
        "unmapped_keywords": dict(sorted(unmapped_kw.items(), key=lambda kv: -kv[1])),
        "first": min((e.timestamp for e in events), default=None),
        "last": max((e.timestamp for e in events), default=None),
    }


def print_summary(s: dict) -> None:
    print(f"records parsed : {s['total']}")
    print(f"time range     : {s['first']} -> {s['last']}")
    print(f"per major_type : {s['by_major']}")
    print(f"UNMAPPED       : {s['unmapped_pct']}%  keywords={s['unmapped_keywords']}")
    print(f"severity       : {s['by_severity']}")


def _dt(v: str) -> datetime:
    return datetime.fromisoformat(v.replace("/", "-"))


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Parse a LOGANALYZER SUMLOG text export into events.db")
    p.add_argument("--file", default=str(DATA_FILE))
    p.add_argument("--db", default=str(DB_PATH))
    p.add_argument("--start-line", type=int)
    p.add_argument("--end-line", type=int)
    p.add_argument("--start-time", type=_dt, help="YYYY-MM-DD[ T]HH:MM:SS")
    p.add_argument("--end-time", type=_dt)
    p.add_argument("--max-records", type=int)
    p.add_argument("--show", type=int, default=0, help="print the first N parsed events")
    p.add_argument("--no-db", action="store_true")
    p.add_argument("--count-all", action="store_true", help="count header-delimited records in the whole file")
    a = p.parse_args(argv)

    spec = SliceSpec(a.start_line, a.end_line, a.start_time, a.end_time, a.max_records)
    events = parse_file(a.file, spec)
    for e in events[: a.show]:
        print(f"{e.event_id} {e.timestamp:%m-%d %H:%M:%S} {e.raw_type_keyword:<6} "
              f"{e.major_type}/{e.minor_type} job={e.job_id} task={e.task_id} sess={e.session_id} "
              f"{e.severity} | {e.raw_text.splitlines()[0][:70]}")
    print_summary(summarize(events))
    if a.count_all:
        n, reported = count_records(a.file)
        print(f"whole-file header-delimited records: {n}  (LOGANALYZER reports {reported})")
    if not a.no_db:
        conn = db.connect(a.db)
        print(f"stored {db.insert_events(conn, events)} events in {a.db}")


if __name__ == "__main__":
    main()
