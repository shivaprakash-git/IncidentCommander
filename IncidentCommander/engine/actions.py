"""Action recommender. risk_level comes ONLY from action_catalog.yaml.

Hypotheses (LLM output) are used for matching text/refs only; nothing the model
returns is ever copied into risk_level, and the catalog is validated on load.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from .config import ROOT

CATALOG_PATH = ROOT / "action_catalog.yaml"
RISK_LEVELS = ("safe", "needs_approval", "forbidden")


@dataclass
class RecommendedAction:
    action_id: str                 # == catalog id (unique per incident)
    title: str
    description: str
    subsystem: str
    risk_level: str                # from the catalog only
    hypothesis_cause: str = ""
    confidence: float = 0.0
    evidence_event_ids: list = field(default_factory=list)
    runbook_refs: list = field(default_factory=list)
    status: str = "pending"        # pending | auto_approved (safe) - set by approval.persist

    def to_dict(self) -> dict:
        return asdict(self)


def load_catalog(path: Path = CATALOG_PATH) -> list:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    seen = set()
    for a in data["actions"]:
        if a["risk_level"] not in RISK_LEVELS:
            raise ValueError(f"catalog action {a['id']}: invalid risk_level {a['risk_level']!r}")
        if a["id"] in seen:
            raise ValueError(f"duplicate catalog id {a['id']}")
        seen.add(a["id"])
    return data["actions"]


def _stem(ref: str) -> str:
    return ref.split("#")[0]


def _match(entry: dict, cause: str, stems: set) -> bool:
    low = cause.lower()
    return any(k.lower() in low for k in entry.get("keywords", [])) or bool(stems & set(entry.get("runbooks", [])))


def _make(entry: dict, cause: str = "", conf: float = 0.0, ev=None, refs=None) -> RecommendedAction:
    return RecommendedAction(entry["id"], entry["title"], entry["description"], entry.get("subsystem", "general"),
                             entry["risk_level"], cause, conf, list(ev or []), list(refs or []))


def recommend_actions(rca_result: dict, catalog: Optional[list] = None) -> list:
    """rca_result = engine.rca.analyze() output. Deterministic; safest actions first."""
    catalog = catalog if catalog is not None else load_catalog()
    picked: dict = {}
    if not rca_result.get("insufficient_evidence"):
        for h in rca_result.get("hypotheses", []):
            stems = {_stem(r) for r in h.get("runbook_refs", [])}
            for entry in catalog:
                if entry.get("fallback") or not _match(entry, h["cause"], stems):
                    continue
                if entry["id"] not in picked or h["confidence"] > picked[entry["id"]].confidence:
                    picked[entry["id"]] = _make(entry, h["cause"], h["confidence"],
                                                h.get("evidence_event_ids"), h.get("runbook_refs"))
    if not picked:                                       # nothing matched or evidence insufficient
        picked = {e["id"]: _make(e, "insufficient evidence for a root cause") for e in catalog if e.get("fallback")}
    order = {r: i for i, r in enumerate(RISK_LEVELS)}
    return sorted(picked.values(), key=lambda a: (order[a.risk_level], -a.confidence, a.action_id))
