"""Orchestration used by the CLI and the API routes (routes stay thin wrappers).

ingest():   parse a bounded slice -> events.db, run discovery, parse the event
            windows around every real candidate (so incidents are analysable
            even when they fall outside the slice), fall back to the synthetic
            generator only if discovery finds fewer than MAX_DEMO candidates.
discover(): full-file keyword scan only.

CLI:  python -m engine.pipeline ingest [--source real|synthetic] [slice flags]
      python -m engine.pipeline discover
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from typing import Optional

from . import approval, db, discovery, generator, precursor
from .config import DATA_FILE, DB_PATH
from .actions import recommend_actions
from .correlation import correlate
from .timeline import build_timeline
from .parser import SliceSpec, _dt, count_records, parse_file, print_summary, summarize


def discover(file=DATA_FILE, db_path=DB_PATH, save: bool = True) -> dict:
    r = discovery.discover(file)
    if save:
        db.save_incidents(db.connect(db_path), r.candidates)
    return {
        "records_scanned": r.records_scanned, "hit_records": len(r.hits),
        "keyword_counts": r.keyword_counts,
        "candidates": [_cand_dict(c) for c in r.candidates],
    }


def _cand_dict(c) -> dict:
    return {
        "incident_id": c.incident_id, "source": c.source, "type": c.type, "demo": c.demo,
        "trigger_event_id": c.trigger_event_id, "trigger_ts": c.trigger_ts.isoformat(),
        "window_start": c.window_start.isoformat(), "window_end": c.window_end.isoformat(),
        "hit_count": len(c.hits), "keywords": c.keywords, "description": c.description,
    }


def ingest(source: str = "real", spec: Optional[SliceSpec] = None, file=DATA_FILE,
           db_path=DB_PATH, reset: bool = True) -> dict:
    """Returns a summary dict (also printed by the CLI)."""
    conn = db.connect(db_path)
    if reset:
        for t in ("events", "incidents", "correlation_runs", "rca_results"):
            conn.execute(f"DELETE FROM {t}")
        conn.commit()
    out: dict = {"source": source, "slice_events": 0, "window_events": 0}
    real_cands: list = []

    if source == "real":
        events = parse_file(file, spec)
        out["slice_events"] = db.insert_events(conn, events)
        out["slice_summary"] = summarize(events)
        r = discovery.discover(file)
        real_cands = r.candidates
        out["discovery"] = {"hit_records": len(r.hits), "keyword_counts": r.keyword_counts,
                            "candidates": len(real_cands), "records_scanned": r.records_scanned}
        for c in real_cands:          # incident windows outside the slice
            win = parse_file(file, SliceSpec(start_time=c.window_start, end_time=c.window_end))
            out["window_events"] += db.insert_events(conn, win)
        db.save_incidents(conn, real_cands)

    demo_real = sum(c.demo for c in real_cands)
    if source == "synthetic" or demo_real < discovery.MAX_DEMO:
        events, cands, _ = generator.generate()
        db.insert_events(conn, events)
        # top up demo set: real demos first, synthetic fill the remainder
        need = discovery.MAX_DEMO - demo_real
        for i, c in enumerate(cands):
            c.demo = i < need
        db.save_incidents(conn, cands)
        out["synthetic_events"] = len(events)
        out["synthetic_incidents"] = [c.incident_id for c in cands if c.demo]
    demo = conn.execute("SELECT incident_id, source, type FROM incidents WHERE demo=1 ORDER BY trigger_ts").fetchall()
    out["demo_incidents"] = [dict(r) for r in demo]
    out["events_total"] = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    pool = parse_file(file, SliceSpec(start_line=1)) if source == "real" else None   # normal-window pool
    out["labeled_set"] = precursor.build_labeled_set(conn, pool)
    return out


def default_incident_id(db_path=DB_PATH) -> str:
    r = db.connect(db_path).execute(
        "SELECT incident_id FROM incidents WHERE demo=1 ORDER BY trigger_ts LIMIT 1").fetchone()
    if not r:
        raise SystemExit("no incidents - run: python -m engine.pipeline ingest")
    return r["incident_id"]


def incident_events(conn, row) -> list:
    return db.load_events(conn, datetime.fromisoformat(row["window_start"]), datetime.fromisoformat(row["window_end"]))


def correlate_incident(conn, incident_id: str, run_quantum: bool = True, refresh: bool = False, **kw) -> dict:
    """Correlation for an incident window, cached in correlation_runs (QAOA is slow)."""
    hit = conn.execute("SELECT result FROM correlation_runs WHERE incident_id=?", (incident_id,)).fetchone()
    if hit and not refresh:
        cached = json.loads(hit["result"])
        if not (run_quantum and cached["qaoa"].get("status") == "skipped"
                and cached["qaoa"].get("reason") == "disabled by caller"):
            return cached
    row = conn.execute("SELECT * FROM incidents WHERE incident_id=?", (incident_id,)).fetchone()
    if not row:
        raise KeyError(incident_id)
    res = correlate(incident_events(conn, row), focus_event_id=row["trigger_event_id"],
                    run_quantum=run_quantum, **kw).to_dict()
    conn.execute("INSERT OR REPLACE INTO correlation_runs VALUES (?,?,?)",
                 (incident_id, datetime.now().isoformat(timespec="seconds"), json.dumps(res)))
    conn.commit()
    return res


def build_incident(incident_id: str, db_path=DB_PATH, run_quantum: bool = True) -> dict:
    """Incident row + correlation + timeline of the trigger event's Louvain cluster
    (whole window if that cluster has fewer than 3 events)."""
    conn = db.connect(db_path)
    row = conn.execute("SELECT * FROM incidents WHERE incident_id=?", (incident_id,)).fetchone()
    if not row:
        raise KeyError(incident_id)
    corr = correlate_incident(conn, incident_id, run_quantum)
    evs = {e.event_id: e for e in incident_events(conn, row)}
    trig = row["trigger_event_id"]
    cid = corr["louvain"].get(trig)
    members = [i for i, c in corr["louvain"].items() if c == cid] if cid is not None else []
    if len(members) < 3:
        members = list(evs)
    timeline = build_timeline([evs[i] for i in members if i in evs], anchor_id=trig)
    return {"incident_id": incident_id, "incident": dict(row), "correlation": corr, "timeline": timeline,
            "cluster_size": len(members)}


def early_warning(incident_id: str, db_path=DB_PATH) -> list:
    return [a.to_dict() for a in precursor.early_warning_for_incident(db.connect(db_path), incident_id)]


def rca_for_incident(incident_id: str, db_path=DB_PATH, refresh: bool = False, **analyze_kw) -> dict:
    """RCA (cached in rca_results). Returns {"rca": ..., "timeline_text": ...}."""
    from . import rca
    conn = db.connect(db_path)
    hit = conn.execute("SELECT result FROM rca_results WHERE incident_id=?", (incident_id,)).fetchone()
    if hit and not refresh:
        return json.loads(hit["result"])
    inc = build_incident(incident_id, db_path, run_quantum=False)
    alerts = precursor.early_warning_for_incident(conn, incident_id)
    out = {"rca": rca.analyze(inc["timeline"], alerts, **analyze_kw),
           "timeline_text": inc["timeline"].to_text(30),
           "precursor_alerts": [a.to_dict() for a in alerts]}
    if not out["rca"].get("transient"):                   # never cache an outage as an answer
        conn.execute("INSERT OR REPLACE INTO rca_results VALUES (?,?,?)",
                     (incident_id, datetime.now().isoformat(timespec="seconds"), json.dumps(out)))
        conn.commit()
    return out


def actions_for_incident(incident_id: str, db_path=DB_PATH) -> list:
    """Recommend (from the cached/new RCA + action_catalog.yaml) and persist; safe ones auto-audit."""
    rca_out = rca_for_incident(incident_id, db_path)
    return approval.persist_recommendations(db.connect(db_path), incident_id, recommend_actions(rca_out["rca"]))


def _print_ingest(o: dict) -> None:
    if "slice_summary" in o:
        print("== default slice =="); print_summary(o["slice_summary"])
        d = o["discovery"]
        print(f"== discovery (full file, {d['records_scanned']} records) ==")
        print(f"hit records: {d['hit_records']}  keywords: {d['keyword_counts']}  candidate windows: {d['candidates']}")
        print(f"window events pulled in for candidates: {o['window_events']}")
    if "synthetic_events" in o:
        print(f"== synthetic fallback used: {o['synthetic_events']} events; demo incidents {o['synthetic_incidents']}")
    real = [d for d in o["demo_incidents"] if d["source"] == "real"]
    syn = [d for d in o["demo_incidents"] if d["source"] == "synthetic"]
    print(f"== demo incidents: {len(real)} real, {len(syn)} synthetic ==")
    for d in o["demo_incidents"]:
        print(f"   {d['incident_id']:<9} [{d['source']}] {d['type']}")
    print(f"events in DB: {o['events_total']}")
    print(f"precursor labelled set: {o['labeled_set']}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Incident Commander pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("ingest")
    pi.add_argument("--source", choices=["real", "synthetic"], default="real")
    pi.add_argument("--start-line", type=int); pi.add_argument("--end-line", type=int)
    pi.add_argument("--start-time", type=_dt); pi.add_argument("--end-time", type=_dt)
    pi.add_argument("--max-records", type=int)
    pi.add_argument("--keep", action="store_true", help="do not clear existing events/incidents")
    sub.add_parser("discover")
    pc = sub.add_parser("count", help="whole-file record count vs LOGANALYZER-reported count")
    a = p.parse_args(argv)
    if a.cmd == "ingest":
        spec = SliceSpec(a.start_line, a.end_line, a.start_time, a.end_time, a.max_records)
        _print_ingest(ingest(a.source, spec, reset=not a.keep))
    elif a.cmd == "discover":
        r = discovery.discover(); discovery.print_report(r)
    else:
        print(count_records())


if __name__ == "__main__":
    main()
