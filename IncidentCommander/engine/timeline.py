"""Timeline builder: order a cluster chronologically and tag trigger / propagation / symptom.

Heuristic (per spec): first event = trigger; the terminal / high-severity event
(halt-load, security violation, error-looking EOT) = symptom; everything else =
propagation. The symptom is the LAST CRIT event, else the last WARN, else the
last event. `anchor_id` (the discovery hit) is only flagged, it does not change roles.

CLI:  python -m engine.timeline [--incident INC-R01]
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from typing import Optional

from . import db
from .config import DB_PATH
from .models import Event

ROUTINE = {"OPEN", "CLOSE", "BOT", "EOT", "EOJ", "BOJ", "INT", "LIB", "TIME", "LOGON", "LGOFF", "DIAG", "->"}


@dataclass
class TimelineEntry:
    event_id: str
    timestamp: str
    role: str                  # trigger | propagation | symptom
    keyword: str
    severity: str
    summary: str
    job_id: Optional[str] = None
    is_anchor: bool = False


@dataclass
class Timeline:
    entries: list = field(default_factory=list)
    trigger_id: Optional[str] = None
    symptom_id: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    duration_s: float = 0.0
    n_events: int = 0

    def salient(self, max_entries: int = 30) -> list:
        """Entries an analyst (or the RCA prompt) should read: trigger, symptom, anchor,
        anything WARN/CRIT or non-routine. Chronological, capped."""
        keep = [e for e in self.entries
                if e.role in ("trigger", "symptom") or e.is_anchor or e.severity != "INFO"
                or e.keyword not in ROUTINE]
        if len(keep) > max_entries:
            must = [e for e in keep if e.role != "propagation" or e.is_anchor or e.severity == "CRIT"]
            rest = [e for e in keep if e not in must]
            keep = sorted(must + rest[: max(0, max_entries - len(must))], key=lambda e: e.timestamp)[:max_entries]
        return keep

    def to_text(self, max_entries: int = 30) -> str:
        return "\n".join(
            f"{e.event_id} {e.timestamp[11:19]} [{e.role}{'*' if e.is_anchor else ''}] "
            f"{e.keyword} {e.severity} :: {e.summary}" for e in self.salient(max_entries))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["entries"] = [asdict(e) for e in self.entries]
        return d


def _summary(e: Event, n: int = 110) -> str:
    return " | ".join(l.strip() for l in e.raw_text.splitlines()[:3])[:n]


def build_timeline(cluster_events: list, anchor_id: Optional[str] = None) -> Timeline:
    evs = sorted(cluster_events, key=lambda e: (e.timestamp, e.line_no))
    if not evs:
        return Timeline()
    sym = None
    for sev in ("CRIT", "WARN"):
        cands = [e for e in evs[1:] if e.severity == sev]
        if cands:
            sym = cands[-1]
            break
    if sym is None and len(evs) > 1:
        sym = evs[-1]
    entries = []
    for i, e in enumerate(evs):
        role = "trigger" if i == 0 else ("symptom" if sym is not None and e.event_id == sym.event_id else "propagation")
        entries.append(TimelineEntry(e.event_id, e.timestamp.isoformat(), role, e.raw_type_keyword,
                                     e.severity, _summary(e), e.job_id, e.event_id == anchor_id))
    return Timeline(entries, evs[0].event_id, sym.event_id if sym else None,
                    evs[0].timestamp.isoformat(), evs[-1].timestamp.isoformat(),
                    (evs[-1].timestamp - evs[0].timestamp).total_seconds(), len(evs))


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Print the timeline of an incident's trigger cluster")
    p.add_argument("--incident")
    p.add_argument("--db", default=str(DB_PATH))
    a = p.parse_args(argv)
    from . import pipeline
    inc = pipeline.build_incident(a.incident or pipeline.default_incident_id(a.db), a.db)
    t = inc["timeline"]
    print(f"incident {inc['incident_id']}: cluster of {t.n_events} events, {t.start} -> {t.end} "
          f"({t.duration_s:.0f}s), trigger={t.trigger_id} symptom={t.symptom_id}")
    print(t.to_text())


if __name__ == "__main__":
    main()
