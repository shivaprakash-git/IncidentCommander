"""RCA agent: retrieve runbook/incident chunks, ask Gemma for forced-JSON hypotheses.

Guard rails (spec):
  * max retrieval similarity < MIN_SIMILARITY  -> insufficient_evidence WITHOUT calling the LLM
  * Gemma may wrap JSON in fences / prose: strip fences, json.loads, retry ONCE with an
    explicit "ONLY valid JSON" follow-up, then fall back to insufficient_evidence
  * evidence_event_ids are kept only if they exist in the timeline and runbook_refs only
    if they were actually retrieved (drops hallucinated references)
  * the model never produces a risk level; that comes from action_catalog.yaml alone

CLI:  python -m engine.rca [--incident INC-R01]
"""
from __future__ import annotations

import argparse
import json
import re
from typing import Callable, Optional

from .config import DB_PATH
from .nim import NimUnavailable

MIN_SIMILARITY = 0.4
TOP_K = 4
TEMPERATURE = 0.2

SYSTEM_PROMPT = (
    "You are an incident root-cause analyst for Unisys ClearPath MCP systems. Use ONLY the timeline "
    "events and the reference excerpts provided. Respond with ONLY a JSON object - no prose, no markdown "
    "fences - of exactly this shape: "
    '{"hypotheses":[{"cause": string, "confidence": number between 0 and 1, '
    '"evidence_event_ids": [string], "runbook_refs": [string]}], "insufficient_evidence": boolean}. '
    "evidence_event_ids must be copied from the timeline ids (e.g. L014393). runbook_refs must be copied "
    "from the excerpt ids (e.g. auth_failure_security_violation#0). If the evidence does not support a "
    "cause, return an empty hypotheses list and insufficient_evidence true. Do not recommend actions or "
    "risk levels."
)
RETRY_PROMPT = "Return ONLY valid JSON matching the required shape, no prose, no markdown fences."


def _insufficient(reason: str, retrieved: list, llm_called: bool = False, transient: bool = False) -> dict:
    """transient=True: an outage / bad model reply, not a verdict on the evidence -> callers must not cache it."""
    return {"hypotheses": [], "insufficient_evidence": True, "reason": reason,
            "retrieved": retrieved, "llm_called": llm_called, "transient": transient}


def extract_json(text: str) -> Optional[dict]:
    """Best-effort: strip fences / surrounding prose, return a dict or None."""
    t = re.sub(r"```(?:json)?", "", text or "").strip()
    for cand in (t, t[t.find("{"): t.rfind("}") + 1] if "{" in t and "}" in t else ""):
        if not cand:
            continue
        try:
            obj = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def validate(obj: dict, event_ids: set, chunk_ids: set) -> Optional[dict]:
    """Coerce to the output schema; None if it is not usable."""
    if not isinstance(obj.get("hypotheses"), list):
        return None
    hyps, dropped = [], 0
    for h in obj["hypotheses"]:
        if not isinstance(h, dict) or not isinstance(h.get("cause"), str) or not h["cause"].strip():
            continue
        try:
            conf = min(1.0, max(0.0, float(h.get("confidence", 0))))
        except (TypeError, ValueError):
            conf = 0.0
        ev = [str(x) for x in h.get("evidence_event_ids") or []]
        refs = [str(x) for x in h.get("runbook_refs") or []]
        dropped += sum(x not in event_ids for x in ev) + sum(x not in chunk_ids for x in refs)
        hyps.append({"cause": h["cause"].strip(), "confidence": round(conf, 3),
                     "evidence_event_ids": [x for x in ev if x in event_ids],
                     "runbook_refs": [x for x in refs if x in chunk_ids]})
    hyps.sort(key=lambda h: -h["confidence"])
    return {"hypotheses": hyps, "insufficient_evidence": bool(obj.get("insufficient_evidence", not hyps)) or not hyps,
            "dropped_references": dropped}


def analyze(timeline, alerts: Optional[list] = None, store=None, chat: Optional[Callable] = None,
            top_k: int = TOP_K, min_similarity: float = MIN_SIMILARITY) -> dict:
    """timeline: engine.timeline.Timeline; alerts: precursor EarlyWarningAlert list (optional context)."""
    if store is None:
        from .rag import build_store
        store = build_store()
    if chat is None:
        from .nim import chat as nim_chat
        chat = nim_chat

    tl_text = timeline.to_text(30)
    alert_text = "; ".join(f"{a.matched_incident_type} (sim {a.similarity_score}) in {a.subsystem}"
                           for a in (alerts or [])) or "none"
    query = f"{tl_text[:1800]}\nPrecursor alerts: {alert_text}"
    try:
        hits = store.query(query, k=top_k)
    except NimUnavailable as exc:
        return _insufficient(f"retrieval unavailable: {exc}", [], transient=True)
    retrieved = [{"chunk_id": cid, "score": round(float(s), 3), "source": (meta or {}).get("source")}
                 for s, cid, _, meta in hits]
    if not hits or hits[0][0] < min_similarity:
        top = f"{hits[0][0]:.3f}" if hits else "n/a"
        return _insufficient(f"max retrieval similarity {top} < {min_similarity}; LLM not called", retrieved)

    excerpts = "\n\n".join(f"[{cid}]\n{text[:1200]}" for _, cid, text, _ in hits)
    user = (f"TIMELINE (salient events, ids in brackets are the event ids):\n{tl_text}\n\n"
            f"PRECURSOR ALERTS: {alert_text}\n\nREFERENCE EXCERPTS:\n{excerpts}")
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]
    event_ids = {e.event_id for e in timeline.entries}
    chunk_ids = {cid for _, cid, _, _ in hits}
    try:
        raw = chat(messages, temperature=TEMPERATURE)
        parsed = extract_json(raw)
        result = validate(parsed, event_ids, chunk_ids) if parsed else None
        if result is None:                                    # one explicit retry
            raw = chat(messages + [{"role": "assistant", "content": raw or ""},
                                   {"role": "user", "content": RETRY_PROMPT}], temperature=TEMPERATURE)
            parsed = extract_json(raw)
            result = validate(parsed, event_ids, chunk_ids) if parsed else None
    except NimUnavailable as exc:
        return _insufficient(f"LLM unavailable: {exc}", retrieved, llm_called=True, transient=True)
    if result is None:
        return _insufficient("LLM did not return valid JSON after one retry", retrieved, llm_called=True, transient=True)
    result.update(retrieved=retrieved, llm_called=True)
    return result


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="RCA for an incident's timeline")
    p.add_argument("--incident")
    p.add_argument("--db", default=str(DB_PATH))
    a = p.parse_args(argv)
    from . import pipeline
    out = pipeline.rca_for_incident(a.incident or pipeline.default_incident_id(a.db), a.db, refresh=True)
    print("== retrieved chunks ==")
    for r in out["rca"]["retrieved"]:
        print(f"  {r['score']:.3f}  {r['chunk_id']}  ({r['source']})")
    print("== timeline given to the model ==")
    print(out["timeline_text"])
    print("== hypothesis JSON ==")
    print(json.dumps({k: v for k, v in out["rca"].items() if k != "retrieved"}, indent=2))


if __name__ == "__main__":
    main()
