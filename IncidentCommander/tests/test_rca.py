from datetime import datetime

import numpy as np

from engine.models import Event
from engine.rag import SimpleVectorStore
from engine.rca import analyze, extract_json
from engine.timeline import build_timeline


def timeline():
    evs = [Event(event_id=f"L{i}", timestamp=datetime(2023, 8, 10, 11, 26, i), job_id="1", task_id="1",
                 session_id=None, major_type="UNMAPPED", minor_type="X", raw_type_keyword="INFO",
                 severity="CRIT" if i == 2 else "INFO", raw_text=f"6619 SECURITY VIOLATION {i}", line_no=i)
           for i in range(3)]
    return build_timeline(evs)


class FakeStore(SimpleVectorStore):
    """Returns canned hits regardless of the query text."""
    def __init__(self, score):
        super().__init__(); self.score = score

    def query(self, q, k=3):
        return [(self.score, "auth_failure_security_violation#0", "runbook text", {"source": "runbooks/a.md"})]


GOOD = ('{"hypotheses":[{"cause":"Bad credentials via NXEDIT","confidence":0.8,'
        '"evidence_event_ids":["L2","L999"],"runbook_refs":["auth_failure_security_violation#0","nope#1"]}],'
        '"insufficient_evidence":false}')


def test_extract_json_strips_fences_and_prose():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! Here it is: {"a": 1} hope that helps') == {"a": 1}
    assert extract_json("no json here") is None


def test_low_similarity_never_calls_llm():
    calls = []
    out = analyze(timeline(), store=FakeStore(0.2), chat=lambda *a, **k: calls.append(1) or GOOD)
    assert out["insufficient_evidence"] is True and out["hypotheses"] == [] and not calls
    assert out["llm_called"] is False


def test_good_answer_drops_hallucinated_references():
    out = analyze(timeline(), store=FakeStore(0.6), chat=lambda *a, **k: "```json\n" + GOOD + "\n```")
    h = out["hypotheses"][0]
    assert h["evidence_event_ids"] == ["L2"] and h["runbook_refs"] == ["auth_failure_security_violation#0"]
    assert out["insufficient_evidence"] is False and out["dropped_references"] == 2


def test_retries_once_then_succeeds_or_falls_back():
    replies = iter(["I think it is credentials.", GOOD])
    seen = []
    out = analyze(timeline(), store=FakeStore(0.6), chat=lambda m, **k: seen.append(m) or next(replies))
    assert len(seen) == 2 and "ONLY valid JSON" in seen[1][-1]["content"]
    assert out["hypotheses"]
    bad = analyze(timeline(), store=FakeStore(0.6), chat=lambda *a, **k: "still prose")
    assert bad["insufficient_evidence"] is True and bad["llm_called"] is True


def test_temperature_is_low_and_no_risk_level_in_output():
    temps = []
    out = analyze(timeline(), store=FakeStore(0.6), chat=lambda m, temperature=None, **k: temps.append(temperature) or GOOD)
    assert temps == [0.2]
    assert "risk_level" not in str(out)


def test_outage_and_bad_json_are_marked_transient_but_low_similarity_is_not():
    from engine.nim import NimUnavailable

    def boom(*a, **k):
        raise NimUnavailable("504")
    assert analyze(timeline(), store=FakeStore(0.6), chat=boom)["transient"] is True
    assert analyze(timeline(), store=FakeStore(0.6), chat=lambda *a, **k: "prose")["transient"] is True
    assert analyze(timeline(), store=FakeStore(0.2), chat=boom)["transient"] is False   # a real verdict
