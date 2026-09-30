"""Precursor matcher: similarity-based early warning (NOT a trained classifier).

For each incident we take the LEAD_MIN minutes of events before its trigger and
turn them into a fixed-length count vector over FEATURES. Those vectors are the
precursor library and also the labelled dataset (pre-incident window = 1,
sampled normal window = 0) that Phase 5.5 (QSVM) reuses. A sliding-window scan
over recent events computes the same signature and emits an alert when the
cosine similarity to a library signature reaches the threshold (default 0.75).

Matching uses log1p(count) * weight over the ANOMALY features only. The
always-present activity features (logons, DIAG, LIB) are stored in the vectors
(QSVM may use them) but weigh 0 for matching: measured on the real file, even at
weight 0.25 they made every normal window look like a precursor (30/30 false
positives). Windows with no anomaly feature never match.

CLI:  python -m engine.precursor --selftest | --build | --scan
"""
from __future__ import annotations

import argparse
import json
import random
import re
from bisect import bisect_left
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Optional

import numpy as np

from . import db
from .config import DATA_FILE, DB_PATH
from .models import Event

LEAD_MIN = 10
THRESHOLD = 0.75


def _has(rx: str):
    r = re.compile(rx, re.IGNORECASE)
    return lambda e: bool(r.search(e.raw_text))


# name, weight, predicate, subsystem
FEATURES = [
    ("security_violation", 1.0, _has(r"SECURITY VIOLATION"), "security/logon"),
    ("invalid_login", 1.0, _has(r"INVALID USERCODE|INCORRECT (?:USERCODE|PASSWORD)"), "security/logon"),
    ("kerberos_gssapi", 1.0, _has(r"GSSAPI|KERBEROS"), "security/logon"),
    ("linkage_failed", 1.0, _has(r"LINKAGE FAILED"), "library/linkage"),
    ("generic_failed", 1.0, lambda e: bool(re.search(r"\bFAILED\b", e.raw_text, re.I))
     and not re.search(r"LINKAGE FAILED|SECURITY VIOLATION", e.raw_text, re.I), "general"),
    ("file_open_failure", 1.0, _has(r"OPEN FAILED|NO DISK SPACE"), "storage"),
    ("disk_low", 1.0, _has(r"SPACE LOW|FAMILY \S+ FULL|SUMLOG DISK"), "storage"),
    ("timeout_lock", 1.0, _has(r"TIMEOUT|LOCK REQUEST"), "database"),
    ("abend_ds", 1.0, _has(r"ABEND|DEADLOCK|DS ED|P-DSED"), "task management"),
    ("crit_events", 1.0, lambda e: e.severity == "CRIT", "general"),
    ("warn_events", 1.0, lambda e: e.severity == "WARN", "general"),
    ("logon_events", 0.0, lambda e: e.raw_type_keyword in ("LOGON", "LGOFF"), "security/logon"),
    ("diag_events", 0.0, lambda e: e.raw_type_keyword == "DIAG", "general"),
    ("lib_events", 0.0, lambda e: e.raw_type_keyword == "LIB", "library/linkage"),
]
FEATURE_NAMES = [f[0] for f in FEATURES]
WEIGHTS = np.array([f[1] for f in FEATURES])


@dataclass
class EarlyWarningAlert:
    subsystem: str
    matched_incident_type: str
    similarity_score: float
    matched_event_ids: list
    window_start: str
    window_end: str
    matched_incident_id: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LibraryEntry:
    incident_id: str
    incident_type: str
    source: str
    vector: list
    window_start: str
    window_end: str


def signature(events: list) -> tuple:
    """-> (count vector, {feature: [event ids that contributed]})"""
    vec = np.zeros(len(FEATURES))
    who: dict = {}
    for e in events:
        for i, (name, _, pred, _) in enumerate(FEATURES):
            if pred(e):
                vec[i] += 1
                who.setdefault(name, []).append(e.event_id)
    return vec, who


def matchable(vec) -> bool:
    """True if the window has at least one anomaly feature (only those count for matching)."""
    return bool(np.any(np.asarray(vec) * WEIGHTS))


def similarity(a, b) -> float:
    a, b = np.log1p(np.asarray(a)) * WEIGHTS, np.log1p(np.asarray(b)) * WEIGHTS
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(a @ b / (na * nb)) if na > 0 and nb > 0 else 0.0


def _slice(events: list, times: list, start: datetime, end: datetime) -> list:
    return events[bisect_left(times, start): bisect_left(times, end)]


def _sorted(events: list) -> tuple:
    ev = sorted(events, key=lambda e: (e.timestamp, e.line_no))
    return ev, [e.timestamp for e in ev]


# ---------------------------------------------------------------- scanning
def scan_for_precursors(recent_events: list, library: list, threshold: float = THRESHOLD,
                        window_min: int = LEAD_MIN, step_min: int = 1,
                        exclude_incident_id: Optional[str] = None) -> list:
    ev, times = _sorted(recent_events)
    lib = [l for l in library if l.incident_id != exclude_incident_id and matchable(l.vector)]
    if not ev or not lib:
        return []
    w = timedelta(minutes=window_min)
    step = timedelta(minutes=step_min)
    first, last = ev[0].timestamp, ev[-1].timestamp
    windows, t = [], first
    while t <= last:
        windows.append((t, t + w))
        t += step
    windows.append((last - w, last + timedelta(microseconds=1)))   # window ending on the newest event
    raw: list = []
    for ws_, we_ in windows:
        win = _slice(ev, times, ws_, we_)
        vec, who = signature(win)
        if matchable(vec):
            best = max(lib, key=lambda l: similarity(vec, l.vector))
            s = similarity(vec, best.vector)
            if s >= threshold:
                ids = sorted({i for lst in who.values() for i in lst})[:20]
                top = max(who, key=lambda n: len(who[n]))
                sub = next(f[3] for f in FEATURES if f[0] == top)
                raw.append((best, s, ids, sub, ws_, we_))
    alerts: list = []                                     # merge contiguous windows per incident type
    for best, s, ids, sub, ws, we in raw:
        prev = alerts[-1] if alerts else None
        if prev and prev.matched_incident_type == best.incident_type and ws <= datetime.fromisoformat(prev.window_end):
            prev.window_end = we.isoformat()
            if s > prev.similarity_score:
                prev.similarity_score, prev.matched_incident_id = round(s, 4), best.incident_id
            prev.matched_event_ids = sorted(set(prev.matched_event_ids) | set(ids))[:20]
        else:
            alerts.append(EarlyWarningAlert(sub, best.incident_type, round(s, 4), ids, ws.isoformat(),
                                            we.isoformat(), best.incident_id))
    return alerts


# ---------------------------------------------------------------- library / labels
def _ensure_table(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS precursor_vectors (
        vector_id TEXT PRIMARY KEY, incident_id TEXT, incident_type TEXT, label INTEGER, source TEXT,
        window_start TEXT, window_end TEXT, features TEXT, feature_names TEXT)""")


def build_labeled_set(conn, all_events: Optional[list] = None, lead_min: int = LEAD_MIN,
                      neg_ratio: int = 3, seed: int = 0) -> dict:
    """Persist positives (pre-trigger window per incident) and sampled normal windows.

    `all_events` = pool to sample normal windows from (whole parsed file for real
    data). Positives always come from the DB. No padding: if the pool is small we
    simply get fewer negatives and report N honestly.
    """
    _ensure_table(conn)
    conn.execute("DELETE FROM precursor_vectors")
    incs = conn.execute("SELECT * FROM incidents ORDER BY trigger_ts").fetchall()
    db_events = db.load_events(conn)
    ev, times = _sorted(db_events)
    lead = timedelta(minutes=lead_min)
    rows, blocked = [], []
    for r in incs:
        trig = datetime.fromisoformat(r["trigger_ts"])
        win = _slice(ev, times, trig - lead, trig)
        vec, _ = signature(win)
        rows.append((f"P-{r['incident_id']}", r["incident_id"], r["type"], 1, r["source"],
                     (trig - lead).isoformat(), trig.isoformat(), json.dumps(vec.tolist()), json.dumps(FEATURE_NAMES)))
        blocked.append((datetime.fromisoformat(r["window_start"]) - lead, datetime.fromisoformat(r["window_end"])))

    pool, ptimes = _sorted(all_events if all_events is not None else db_events)
    rng = random.Random(seed)
    want, negs, tries = neg_ratio * len(incs), 0, 0
    while negs < want and tries < 5000 and pool:
        tries += 1
        s = rng.choice(pool).timestamp
        e_ = s + lead
        if any(s < b1 and e_ > b0 for b0, b1 in blocked):
            continue
        win = _slice(pool, ptimes, s, e_)
        if len(win) < 10:
            continue
        vec, _ = signature(win)
        negs += 1
        rows.append((f"N-{negs:03d}", None, "normal", 0, "real" if all_events is not None else "db",
                     s.isoformat(), e_.isoformat(), json.dumps(vec.tolist()), json.dumps(FEATURE_NAMES)))
    conn.executemany("INSERT INTO precursor_vectors VALUES (?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    return {"positives": len(incs), "negatives": negs, "n_total": len(rows)}


def load_library(conn) -> list:
    _ensure_table(conn)
    return [LibraryEntry(r["incident_id"], r["incident_type"], r["source"], json.loads(r["features"]),
                         r["window_start"], r["window_end"])
            for r in conn.execute("SELECT * FROM precursor_vectors WHERE label=1")]


def load_labeled(conn) -> tuple:
    """-> (X, y, names, meta) for Phase 5.5."""
    _ensure_table(conn)
    rows = conn.execute("SELECT * FROM precursor_vectors ORDER BY vector_id").fetchall()
    return (np.array([json.loads(r["features"]) for r in rows]), np.array([r["label"] for r in rows]),
            FEATURE_NAMES, [dict(r) for r in rows])


# ---------------------------------------------------------------- incident-level helpers
def early_warning_for_incident(conn, incident_id: str, lookback_min: int = 30,
                               threshold: float = THRESHOLD) -> list:
    """Alerts that would have fired in the lookback before this incident's trigger,
    matched against the library WITHOUT the incident's own signature (no self-match)."""
    r = conn.execute("SELECT * FROM incidents WHERE incident_id=?", (incident_id,)).fetchone()
    if not r:
        return []
    trig = datetime.fromisoformat(r["trigger_ts"])
    evs = db.load_events(conn, trig - timedelta(minutes=lookback_min), trig - timedelta(microseconds=1))
    return scan_for_precursors(evs, load_library(conn), threshold, exclude_incident_id=incident_id)


def recent_predictions(conn, minutes: int = 60, threshold: float = THRESHOLD) -> list:
    last = conn.execute("SELECT MAX(timestamp) m FROM events").fetchone()["m"]
    if not last:
        return []
    end = datetime.fromisoformat(last)
    evs = db.load_events(conn, end - timedelta(minutes=minutes), end)
    return scan_for_precursors(evs, load_library(conn), threshold)


# ---------------------------------------------------------------- CLI
def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Precursor library / early-warning scan")
    p.add_argument("--db", default=str(DB_PATH))
    p.add_argument("--build", action="store_true", help="(re)build library + labelled vectors")
    p.add_argument("--selftest", action="store_true", help="each incident's own precursor window vs the library")
    p.add_argument("--scan", action="store_true", help="scan the most recent hour of events")
    p.add_argument("--real-negatives", action="store_true", help="sample normal windows from the whole real file")
    a = p.parse_args(argv)
    conn = db.connect(a.db)
    if a.build:
        pool = None
        if a.real_negatives:
            from .parser import SliceSpec, parse_file
            pool = parse_file(DATA_FILE, SliceSpec(start_line=1))
        print(build_labeled_set(conn, pool))
    lib = load_library(conn)
    if a.selftest:
        print(f"library: {len(lib)} signatures, features={FEATURE_NAMES}")
        for l in lib:
            own = similarity(l.vector, l.vector) if matchable(l.vector) else None
            others = [(similarity(l.vector, m.vector), m.incident_id) for m in lib if m is not l and matchable(m.vector)]
            best = max(others, default=(0, "-"))
            print(f"  {l.incident_id} {l.incident_type:<34} nonzero={sum(1 for v in l.vector if v)} "
                  f"self={own if own is None else round(own, 3)} nearest-other={best[1]}:{best[0]:.2f}")
    if a.scan:
        for al in recent_predictions(conn):
            print(al.to_dict())


if __name__ == "__main__":
    main()
