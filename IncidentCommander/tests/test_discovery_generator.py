from pathlib import Path

from engine.discovery import discover
from engine.generator import generate
from engine.parser import summarize

FIXTURE = Path(__file__).parent / "fixtures" / "mini_sumlog.txt"


def test_discovery_finds_security_violation_and_ignores_noise():
    r = discover(FIXTURE)
    # "NO SUMLOG ENTRIES WERE DISCARDED" banner and the HALT/LOAD UNIT block are noise
    assert "DISCARD" not in r.keyword_counts and "HALT" not in r.keyword_counts
    assert len(r.candidates) == 1
    c = r.candidates[0]
    assert c.type == "auth_failure_security_violation"
    assert c.trigger_event_id == "L000019"
    assert (c.window_end - c.window_start).total_seconds() == 30 * 60
    assert c.demo


def test_generator_is_deterministic_and_schema_faithful():
    ev1, c1, _ = generate(7)
    ev2, c2, _ = generate(7)
    assert [e.event_id for e in ev1] == [e.event_id for e in ev2]
    assert len(c1) == 3 and 100 > len(ev1) >= 40 + 15
    ids = {e.event_id for e in ev1}
    for c in c1:
        assert c.trigger_event_id in ids and c.source == "synthetic"
    s = summarize(ev1)
    assert s["by_severity"].get("CRIT", 0) >= 3        # one planted symptom per scenario
    assert all(e.source == "synthetic" for e in ev1)
