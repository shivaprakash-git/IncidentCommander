from datetime import datetime

from engine import db
from engine.generator import generate
from engine.pipeline import build_incident, ingest
from engine.precursor import (FEATURE_NAMES, build_labeled_set, early_warning_for_incident, load_labeled,
                              load_library, scan_for_precursors, signature, similarity)
from engine.timeline import build_timeline


def synth_db(tmp_path):
    p = tmp_path / "e.db"
    ingest("synthetic", db_path=p)
    return p, db.connect(p)


def test_timeline_roles():
    evs, cands, _ = generate(7)
    c = cands[1]                                    # auth scenario
    window = [e for e in evs if c.window_start <= e.timestamp <= c.window_end]
    t = build_timeline(window, anchor_id=c.trigger_event_id)
    roles = [e.role for e in t.entries]
    assert roles[0] == "trigger" and roles.count("trigger") == 1 and roles.count("symptom") == 1
    assert next(e for e in t.entries if e.event_id == t.symptom_id).severity == "CRIT"
    assert any(e.is_anchor for e in t.entries)
    assert "[trigger" in t.to_text()


def test_precursor_selfmatch_is_one_and_excluding_self_is_lower(tmp_path):
    p, conn = synth_db(tmp_path)
    info = build_labeled_set(conn)
    assert info["positives"] == 3
    lib = load_library(conn)
    assert len(lib) == 3 and all(any(l.vector) for l in lib)          # planted precursors are non-zero
    for l in lib:
        assert abs(similarity(l.vector, l.vector) - 1.0) < 1e-9
    # scanning an incident's own precursor window against the library (self included) flags it
    inc = conn.execute("SELECT * FROM incidents ORDER BY trigger_ts").fetchall()[0]
    evs = db.load_events(conn, datetime.fromisoformat(inc["window_start"]), datetime.fromisoformat(inc["trigger_ts"]))
    alerts = scan_for_precursors(evs, lib)
    assert alerts and alerts[0].similarity_score > 0.95 and alerts[0].matched_incident_type == inc["type"]
    assert set(alerts[0].to_dict()) >= {"subsystem", "matched_incident_type", "similarity_score",
                                        "matched_event_ids", "window_start", "window_end"}
    # leave-one-out helper never matches the incident against itself
    for a in early_warning_for_incident(conn, inc["incident_id"]):
        assert a.matched_incident_id != inc["incident_id"]


def test_zero_windows_never_match_and_features_fixed_length():
    assert similarity([0] * len(FEATURE_NAMES), [1] * len(FEATURE_NAMES)) == 0.0
    v, _ = signature([])
    assert len(v) == len(FEATURE_NAMES) == 14


def test_labeled_set_persisted_for_qsvm(tmp_path):
    p, conn = synth_db(tmp_path)
    build_labeled_set(conn)
    X, y, names, meta = load_labeled(conn)
    assert X.shape[1] == len(names) and set(y) <= {0, 1} and y.sum() == 3


def test_build_incident_end_to_end_without_quantum(tmp_path):
    p, conn = synth_db(tmp_path)
    inc_id = conn.execute("SELECT incident_id FROM incidents ORDER BY trigger_ts LIMIT 1").fetchone()[0]
    out = build_incident(inc_id, p, run_quantum=False)
    assert out["timeline"].n_events >= 3 and out["correlation"]["qaoa"]["status"] == "skipped"
