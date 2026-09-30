"""Synthetic fallback: 3 planted scenarios + ~50 background events.

Only used when real discovery yields fewer than 3 candidates (or when
/ingest is called with source=synthetic). Schema-faithful by construction:
we render LOGANALYZER-style text and feed it through the real parser, so a
synthetic event is indistinguishable in shape from a parsed real one.

CLI:  python -m engine.generator [--save] [--dump synthetic_sumlog.txt]
"""
from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta

from . import db
from .config import DB_PATH
from .models import Candidate
from .parser import parse_lines

DAY = datetime(2023, 8, 15)          # a Tuesday
ID_PREFIX = "S-L"
PAD = " " * 26


def _t(h, m, s=0):
    return DAY.replace(hour=h, minute=m, second=s)


def _item(ts, kw, num, text, cont=(), tag=None):
    return {"ts": ts, "kw": kw, "num": num, "text": text, "cont": list(cont), "tag": tag}


def _scenario_db_lock(seed_ts):
    """DB lock contention cascade: lock timeouts -> waiting tasks -> deadlock ABEND."""
    it = [_item(seed_ts - timedelta(minutes=m), "", 7100, f"DMSII LOCK REQUEST FAILED - RETRY {r} ON STRUCTURE ACCOUNTS",
                ["DATABASE: BANKDB  STRUCTURE: ACCOUNTS"]) for m, r in ((6, 1), (3, 2))]
    it += [_item(seed_ts, "", 7101, "DMSII LOCK REQUEST FAILED - TIMEOUT ON STRUCTURE ACCOUNTS",
                ["DATABASE: BANKDB  STRUCTURE: ACCOUNTS", "USERCODE: BATCH1.  MCS NUMBER: 3  LSN NUMBER: 41"], "trigger")]
    for i, task in enumerate((7102, 7103, 7104, 7105)):
        it.append(_item(seed_ts + timedelta(seconds=40 * (i + 1)), "", task,
                        "DMSII LOCK REQUEST FAILED - WAITING FOR TASK 7101",
                        ["DATABASE: BANKDB  STRUCTURE: ACCOUNTS", "USERCODE: BATCH1.  MCS NUMBER: 3  LSN NUMBER: 41"]))
    it.append(_item(seed_ts + timedelta(seconds=240), "EOT", 7104,
                    "TASKNAME: *DB/UPDATE/PROCESS.  ABEND: DEADLOCK VICTIM",
                    ["HISTORY: DS ED - DMSII DEADLOCK DETECTED", "JOB NUMBER: 7100"], "symptom"))
    return it


def _scenario_auth(seed_ts):
    """Repeated auth failure -> security violation -> halt/load."""
    it = [_item(seed_ts - timedelta(minutes=m), "", 7190 + m, "MCS SECURITY WARNING: INVALID USERCODE/PASSWORD AT LOG ON",
                ["USERCODE: TESTUSR1.", "ORIGINATING LSN: 52   ORIGINATING MCS: 8"]) for m in (5, 2)]
    for i in range(5):
        it.append(_item(seed_ts + timedelta(seconds=70 * i), "", 7201 + i,
                        "SECURITY VIOLATION - INCORRECT PASSWORD",
                        ["VIOLATION CODE: 10", "USERCODE: TESTUSR1.", "STATION NAME: NXEDIT/IP10_32_198_150/1",
                         "ORIGINATING LSN: 52   ORIGINATING MCS: 8"], "trigger" if i == 0 else None))
    it.append(_item(seed_ts + timedelta(seconds=380), "", 7206,
                    "MCS SECURITY VIOLATION: INVALID USERCODE/PASSWORD AT LOG ON",
                    ["USERCODE: TESTUSR1.", "ORIGINATING LSN: 52   ORIGINATING MCS: 8"]))
    it.append(_item(seed_ts + timedelta(seconds=470), "", 7207,
                    "SECURITY VIOLATION - USERCODE SUSPENDED; OPERATOR HALT/LOAD REQUESTED",
                    ["VIOLATION CODE: 12", "ERROR ITEM: TESTUSR1."], "symptom"))
    return it


def _scenario_disk(seed_ts):
    """Disk capacity -> file-open failures."""
    it = [_item(seed_ts - timedelta(minutes=8), "DISK", 7300, "FAMILY USERPK SPACE LOW: 91% OF AREAS IN USE",
                ["UNIT: 1002  FREE SECTORS: 90100"]),
          _item(seed_ts - timedelta(minutes=3), "OPEN", 7299, "EXT NAME: (BATCH)REPORT/TMP.  OPEN FAILED: NO DISK SPACE AVAILABLE",
                ["FAMILY NAME: USERPK", "JOB NUMBER: 7290"])]
    it += [_item(seed_ts, "DISK", 7301, "FAMILY USERPK SPACE LOW: 97% OF AREAS IN USE",
                ["UNIT: 1002  FREE SECTORS: 41200"], "trigger")]
    for i in range(6):
        it.append(_item(seed_ts + timedelta(seconds=55 * (i + 1)), "OPEN", 7310 + i,
                        "EXT NAME: (BATCH)REPORT/OUT.  OPEN FAILED: NO DISK SPACE AVAILABLE",
                        ["INT NAME: REPORTFILE.", "FAMILY NAME: USERPK", "USE = OUT, OPENTYPE: WAIT",
                         "JOB NUMBER: 7300"]))
    it.append(_item(seed_ts + timedelta(seconds=400), "", 7320,
                    "ERROR: SUMLOG DISK FAMILY FULL - ENTRIES BEING DISCARDED",
                    ["FAMILY NAME: USERPK"], "symptom"))
    return it


def _background(rng, start, n):
    kinds = [("OPEN", "EXT NAME: (USR)DATAFILE{n}.", ["INT NAME: DATAFILE.", "FAMILY NAME: USERPK"]),
             ("CLOSE", "EXT NAME: (USR)DATAFILE{n}.", ["CLOSE TYPE: NORMAL  ASSOCIATION: RETAIN"]),
             ("BOT", "TASKNAME: *SYSTEM/UTIL{n}.", ["USERCODE: OPER1.  MCS NUMBER: 1  LSN NUMBER: 10"]),
             ("EOT", "TASKNAME: *SYSTEM/UTIL{n}.", ["USERCODE: OPER1.  MCS NUMBER: 1  LSN NUMBER: 10"]),
             ("LOGON", "USERCODE: OPER{n}.  CHARGECODE: ASW.", []),
             ("LGOFF", "USERCODE: OPER{n}.  CHARGECODE: ASW.", []),
             ("LIB", "*SYSTEM/SUPPORT{n}.   (STACK 00A{n})", [])]
    out = []
    for i in range(n):
        kw, text, cont = rng.choice(kinds)
        k = rng.randint(1, 9)
        out.append(_item(start + timedelta(seconds=rng.randint(0, 1700)), kw, 7000 + rng.randint(1, 60),
                         text.format(n=k), cont))
    return out


def _render(items):
    items = sorted(items, key=lambda x: x["ts"])
    lines = [DAY.strftime("%A, %B %d, %Y")]
    for x in items:
        hh = f"{x['ts']:%H:%M:%S}"
        if x["kw"]:
            lines.append(f"   {hh}   {x['kw']:>6}  {x['num']:>4} {x['text']}")
        else:
            lines.append(f"   {hh}          {x['num']} {x['text']}")
        if x["tag"]:
            x["_line"] = len(lines)
        lines.extend(PAD + c for c in x["cont"])
    return lines


def generate(seed: int = 7):
    """-> (events, candidates, text_lines). Deterministic for a given seed."""
    rng = random.Random(seed)
    specs = [
        ("db_lock_contention_cascade", _scenario_db_lock, _t(9, 10)),
        ("auth_failure_security_violation_halt", _scenario_auth, _t(11, 10)),
        ("disk_capacity_file_open_failures", _scenario_disk, _t(14, 5)),
    ]
    items, meta = [], []
    for name, fn, t0 in specs:
        sc = fn(t0)
        items += sc + _background(rng, t0 - timedelta(minutes=12), 17)
        meta.append((name, sc))
    lines = _render(items)
    events = parse_lines(lines, source="synthetic", id_prefix=ID_PREFIX)
    cands = []
    for i, (name, sc) in enumerate(meta, 1):
        trig = next(x for x in sc if x["tag"] == "trigger")
        sym = next(x for x in sc if x["tag"] == "symptom")
        cands.append(Candidate(
            incident_id=f"INC-S{i:02d}", source="synthetic", type=name,
            trigger_ts=trig["ts"], window_start=trig["ts"] - timedelta(minutes=15),
            window_end=sym["ts"] + timedelta(minutes=15),
            trigger_event_id=f"{ID_PREFIX}{trig['_line']:06d}", demo=True,
            description=f"synthetic planted scenario: {name}",
        ))
    return events, cands, lines


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Synthetic SUMLOG scenario generator")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--save", action="store_true")
    p.add_argument("--dump", help="write the rendered LOGANALYZER-style text here")
    p.add_argument("--db", default=str(DB_PATH))
    a = p.parse_args(argv)
    events, cands, lines = generate(a.seed)
    print(f"{len(events)} synthetic events, {len(cands)} planted incidents")
    for c in cands:
        print(f"  {c.incident_id} {c.type:<40} trigger {c.trigger_ts:%H:%M:%S} {c.trigger_event_id}")
    if a.dump:
        open(a.dump, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    if a.save:
        conn = db.connect(a.db)
        db.insert_events(conn, events)
        db.save_incidents(conn, cands)
        print("saved")


if __name__ == "__main__":
    main()
