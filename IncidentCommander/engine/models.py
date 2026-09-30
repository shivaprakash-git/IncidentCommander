"""Shared data types."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Event:
    event_id: str                      # "L<line number of header>" (real) or "S<n>-L<line>" (synthetic)
    timestamp: datetime
    job_id: Optional[str]
    task_id: Optional[str]
    session_id: Optional[str]
    major_type: str
    minor_type: str
    raw_type_keyword: str
    raw_fields: dict = field(default_factory=dict)
    severity: str = "INFO"             # CRIT | WARN | INFO
    raw_text: str = ""
    source: str = "real"               # real | synthetic
    line_no: int = 0

    def as_row(self) -> tuple:
        return (
            self.event_id, self.timestamp.isoformat(timespec="microseconds"),
            self.job_id, self.task_id, self.session_id,
            self.major_type, self.minor_type, self.raw_type_keyword,
            json.dumps(self.raw_fields, ensure_ascii=False), self.severity,
            self.raw_text, self.source, self.line_no,
        )

    @classmethod
    def from_row(cls, r) -> "Event":
        return cls(
            event_id=r["event_id"], timestamp=datetime.fromisoformat(r["timestamp"]),
            job_id=r["job_id"], task_id=r["task_id"], session_id=r["session_id"],
            major_type=r["major_type"], minor_type=r["minor_type"],
            raw_type_keyword=r["raw_type_keyword"], raw_fields=json.loads(r["raw_fields"] or "{}"),
            severity=r["severity"], raw_text=r["raw_text"], source=r["source"], line_no=r["line_no"],
        )


@dataclass
class Hit:
    line_no: int
    keyword: str            # primary (highest weight) keyword
    keywords: list
    timestamp: datetime
    text: str


@dataclass
class Candidate:
    """A candidate incident window from discovery (or a synthetic scenario)."""
    incident_id: str
    source: str             # real | synthetic
    type: str
    trigger_ts: datetime
    window_start: datetime
    window_end: datetime
    hits: list = field(default_factory=list)
    trigger_event_id: Optional[str] = None
    demo: bool = False
    description: str = ""

    @property
    def keywords(self) -> list:
        return sorted({k for h in self.hits for k in h.keywords})
