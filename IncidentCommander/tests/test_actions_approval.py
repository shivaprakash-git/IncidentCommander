import sqlite3

import pytest

from engine import approval
from engine.actions import RISK_LEVELS, load_catalog, recommend_actions

RCA = {"insufficient_evidence": False, "hypotheses": [{
    "cause": "Kerberos/GSSAPI misconfiguration causing repeated SECURITY VIOLATION on logon",
    "confidence": 0.9, "evidence_event_ids": ["L1", "L2"], "runbook_refs": ["auth_failure_security_violation#0"],
    "risk_level": "safe"}]}                     # a model-supplied label must be ignored


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    return c


def test_catalog_valid_and_risk_only_from_catalog():
    cat = load_catalog()
    assert {a["risk_level"] for a in cat} <= set(RISK_LEVELS)
    recs = recommend_actions({**RCA, "hypotheses": [{**RCA["hypotheses"][0], "risk_level": "forbidden"}]}, cat)
    by_id = {a["id"]: a["risk_level"] for a in cat}
    assert recs and all(r.risk_level == by_id[r.action_id] for r in recs)
    assert {"safe", "needs_approval"} <= {r.risk_level for r in recs}


def test_bad_catalog_risk_level_rejected(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("actions:\n  - {id: x, title: t, description: d, risk_level: llm_says_fine}\n")
    with pytest.raises(ValueError):
        load_catalog(p)


def test_insufficient_evidence_offers_only_safe_fallback():
    recs = recommend_actions({"insufficient_evidence": True, "hypotheses": []})
    assert [r.action_id for r in recs] == ["gather_more_diagnostics"] and recs[0].risk_level == "safe"


def test_safe_actions_auto_approved_and_audited_never_pending(conn):
    rows = approval.persist_recommendations(conn, "I1", recommend_actions(RCA))
    safe = [r for r in rows if r["risk_level"] == "safe"]
    assert safe and all(r["status"] == "auto_approved" for r in safe)
    audit = approval.audit_entries(conn, "I1")
    assert {e["decision"] for e in audit} == {"auto-approved"} and all(e["operator"] == "system" for e in audit)
    with pytest.raises(approval.StateError):
        approval.decide(conn, "I1", safe[0]["action_id"], "approve")


def test_full_cycle_approve_writes_audit_entry(conn):
    rows = approval.persist_recommendations(conn, "I1", recommend_actions(RCA))
    tgt = next(r for r in rows if r["risk_level"] == "needs_approval")
    assert tgt["status"] == "pending"
    out = approval.decide(conn, "I1", tgt["action_id"], "approve", "alice")
    assert out["status"] == "approved"
    e = approval.audit_entries(conn, "I1")[0]
    assert (e["operator"], e["action_id"], e["decision"]) == ("alice", tgt["action_id"], "approved")
    assert e["evidence_shown"]["evidence_event_ids"] == ["L1", "L2"]
    with pytest.raises(approval.StateError):                     # terminal
        approval.decide(conn, "I1", tgt["action_id"], "reject")


def test_reject_and_escalate(conn):
    rows = approval.persist_recommendations(conn, "I1", recommend_actions(RCA))
    need = [r for r in rows if r["risk_level"] == "needs_approval"]
    assert approval.decide(conn, "I1", need[0]["action_id"], "reject")["status"] == "rejected"
    assert approval.decide(conn, "I1", need[1]["action_id"], "escalate")["status"] == "escalated"


def test_forbidden_is_escalate_only(conn):
    rca = {"insufficient_evidence": False, "hypotheses": [{
        "cause": "System hang after SUMLOG full", "confidence": 0.7, "evidence_event_ids": [],
        "runbook_refs": ["halt_load_recovery#0"]}]}
    rows = approval.persist_recommendations(conn, "I2", recommend_actions(rca))
    f = next(r for r in rows if r["risk_level"] == "forbidden")
    for d in ("approve", "reject"):
        with pytest.raises(approval.StateError):
            approval.decide(conn, "I2", f["action_id"], d)
    assert approval.decide(conn, "I2", f["action_id"], "escalate")["status"] == "escalated"


def test_persist_is_idempotent_and_keeps_status(conn):
    recs = recommend_actions(RCA)
    rows = approval.persist_recommendations(conn, "I1", recs)
    tgt = next(r for r in rows if r["risk_level"] == "needs_approval")
    approval.decide(conn, "I1", tgt["action_id"], "approve")
    n = len(approval.audit_entries(conn))
    rows2 = approval.persist_recommendations(conn, "I1", recs)
    assert next(r for r in rows2 if r["action_id"] == tgt["action_id"])["status"] == "approved"
    assert len(approval.audit_entries(conn)) == n


def test_audit_log_is_append_only_at_db_layer(conn):
    approval.persist_recommendations(conn, "I1", recommend_actions(RCA))
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("UPDATE audit_log SET operator='mallory'")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("DELETE FROM audit_log")


def test_unknown_action(conn):
    approval.init(conn)
    with pytest.raises(KeyError):
        approval.decide(conn, "I1", "nope", "approve")
