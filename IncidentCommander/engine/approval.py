"""Approval workflow + append-only audit log.

  safe            -> stored as auto_approved and logged 'auto-approved' (operator 'system'); no gate
  needs_approval  -> pending -> approved | rejected | escalated   (all terminal in v1)
  forbidden       -> pending -> escalated only (approve/reject refused)

`audit_log` is append-only at the DB layer: BEFORE UPDATE / BEFORE DELETE
triggers ABORT, and this module has no update/delete path for it.

CLI:  python -m engine.approval --demo   (full RCA -> action -> approve -> audit cycle on a temp DB)
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS actions (
    incident_id TEXT, action_id TEXT, title TEXT, description TEXT, subsystem TEXT,
    risk_level TEXT, status TEXT, hypothesis_cause TEXT, confidence REAL,
    evidence_event_ids TEXT, runbook_refs TEXT, created TEXT,
    PRIMARY KEY (incident_id, action_id)
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, operator TEXT NOT NULL,
    incident_id TEXT, action_id TEXT, decision TEXT NOT NULL, evidence_shown TEXT
);
CREATE TRIGGER IF NOT EXISTS audit_log_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_log_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
"""

DECISIONS = {"approve": "approved", "reject": "rejected", "escalate": "escalated"}


class StateError(Exception):
    """Illegal transition (API maps to HTTP 409)."""


def init(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _audit(conn, operator, incident_id, action_id, decision, evidence) -> None:
    conn.execute("INSERT INTO audit_log (timestamp, operator, incident_id, action_id, decision, evidence_shown) "
                 "VALUES (?,?,?,?,?,?)", (_now(), operator, incident_id, action_id, decision, json.dumps(evidence)))


def _evidence(row_or_action) -> dict:
    g = row_or_action.__getitem__ if isinstance(row_or_action, sqlite3.Row) else lambda k: getattr(row_or_action, k)
    ev, refs = g("evidence_event_ids"), g("runbook_refs")
    return {"hypothesis": g("hypothesis_cause"), "confidence": g("confidence"),
            "evidence_event_ids": json.loads(ev) if isinstance(ev, str) else ev,
            "runbook_refs": json.loads(refs) if isinstance(refs, str) else refs}


def persist_recommendations(conn, incident_id: str, recs: list) -> list:
    """Idempotent: existing actions keep their status. New safe actions are auto-approved
    and audited; the rest start pending. Returns the stored rows as dicts."""
    init(conn)
    for r in recs:
        status = "auto_approved" if r.risk_level == "safe" else "pending"
        cur = conn.execute(
            "INSERT OR IGNORE INTO actions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (incident_id, r.action_id, r.title, r.description, r.subsystem, r.risk_level, status,
             r.hypothesis_cause, r.confidence, json.dumps(r.evidence_event_ids), json.dumps(r.runbook_refs), _now()))
        if cur.rowcount and status == "auto_approved":
            _audit(conn, "system", incident_id, r.action_id, "auto-approved", _evidence(r))
    conn.commit()
    return list_actions(conn, incident_id)


def list_actions(conn, incident_id: str) -> list:
    init(conn)
    rows = conn.execute("SELECT * FROM actions WHERE incident_id=? ORDER BY "
                        "CASE risk_level WHEN 'safe' THEN 0 WHEN 'needs_approval' THEN 1 ELSE 2 END, action_id",
                        (incident_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["evidence_event_ids"] = json.loads(d["evidence_event_ids"])
        d["runbook_refs"] = json.loads(d["runbook_refs"])
        out.append(d)
    return out


def decide(conn, incident_id: str, action_id: str, decision: str, operator: str = "operator") -> dict:
    """decision in approve | reject | escalate."""
    init(conn)
    if decision not in DECISIONS:
        raise ValueError(f"unknown decision {decision!r}")
    row = conn.execute("SELECT * FROM actions WHERE incident_id=? AND action_id=?", (incident_id, action_id)).fetchone()
    if row is None:
        raise KeyError(action_id)
    if row["risk_level"] == "safe":
        raise StateError("safe actions are informational and never enter the approval queue")
    if row["status"] != "pending":
        raise StateError(f"action already {row['status']}")
    if row["risk_level"] == "forbidden" and decision != "escalate":
        raise StateError("forbidden actions can only be escalated")
    new = DECISIONS[decision]
    with conn:                                            # status change + audit row commit together
        conn.execute("UPDATE actions SET status=? WHERE incident_id=? AND action_id=?", (new, incident_id, action_id))
        _audit(conn, operator, incident_id, action_id, new, _evidence(row))
    return next(a for a in list_actions(conn, incident_id) if a["action_id"] == action_id)


def audit_entries(conn, incident_id: Optional[str] = None, limit: int = 500) -> list:
    init(conn)
    q, args = "SELECT * FROM audit_log", []
    if incident_id:
        q += " WHERE incident_id=?"; args.append(incident_id)
    rows = conn.execute(q + " ORDER BY id DESC LIMIT ?", args + [limit]).fetchall()
    return [{**dict(r), "evidence_shown": json.loads(r["evidence_shown"] or "{}")} for r in rows]


def _demo() -> None:
    import tempfile
    from pathlib import Path

    from .actions import recommend_actions
    conn = sqlite3.connect(str(Path(tempfile.mkdtemp()) / "demo.db"))
    conn.row_factory = sqlite3.Row
    rca = {"insufficient_evidence": False, "hypotheses": [{
        "cause": "Repeated SECURITY VIOLATION from invalid usercode AMURAKI1 via NXEDIT; GSSAPI link failed",
        "confidence": 0.8, "evidence_event_ids": ["L014393", "L014398"],
        "runbook_refs": ["auth_failure_security_violation#0"]}]}
    recs = recommend_actions(rca)
    print("recommended:", [(r.action_id, r.risk_level) for r in recs])
    stored = persist_recommendations(conn, "DEMO-1", recs)
    target = next(a for a in stored if a["risk_level"] == "needs_approval")
    print("approving:", target["action_id"], "->", decide(conn, "DEMO-1", target["action_id"], "approve", "alice")["status"])
    for e in audit_entries(conn, "DEMO-1"):
        print("audit:", e["timestamp"], e["operator"], e["action_id"], e["decision"])
    try:
        conn.execute("DELETE FROM audit_log")
    except sqlite3.DatabaseError as exc:
        print("delete refused:", exc)


if __name__ == "__main__":
    argparse.ArgumentParser(description="approval workflow").add_argument("--demo", action="store_true")
    _demo()
