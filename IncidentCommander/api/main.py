"""Thin FastAPI layer. Every route delegates to engine/ modules; no business logic here.

Run:  uvicorn api.main:app --port 8000
(`operator` is a placeholder identity, not authentication.)
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import Body, FastAPI, HTTPException, Query

from engine import approval, db, pipeline, precursor, qsvm
from engine.config import DB_PATH
from engine.parser import SliceSpec


def _conn():
    return db.connect(DB_PATH)


def _incident_or_404(incident_id: str):
    row = _conn().execute("SELECT * FROM incidents WHERE incident_id=?", (incident_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"unknown incident {incident_id}")
    return row


def create_app() -> FastAPI:
    app = FastAPI(title="Agentic Incident Commander - engine API", version="1.0")

    @app.post("/ingest")
    def ingest(source: str = Query("real", pattern="^(real|synthetic)$"),
               start_line: Optional[int] = None, end_line: Optional[int] = None,
               start_time: Optional[datetime] = None, end_time: Optional[datetime] = None,
               max_records: Optional[int] = None):
        out = pipeline.ingest(source, SliceSpec(start_line, end_line, start_time, end_time, max_records),
                              db_path=DB_PATH)
        out.pop("slice_summary", None) if source != "real" else None
        return _jsonable(out)

    @app.post("/discover")
    def discover():
        return pipeline.discover(db_path=DB_PATH)

    @app.get("/incidents")
    def incidents(demo_only: bool = False):
        q = "SELECT * FROM incidents" + (" WHERE demo=1" if demo_only else "") + " ORDER BY trigger_ts"
        return [dict(r) for r in _conn().execute(q)]

    @app.get("/incidents/{incident_id}/timeline")
    def timeline(incident_id: str, quantum: bool = False):
        _incident_or_404(incident_id)
        inc = pipeline.build_incident(incident_id, DB_PATH, run_quantum=quantum)
        c = inc["correlation"]
        return {"incident": inc["incident"], "cluster_size": inc["cluster_size"],
                "timeline": inc["timeline"].to_dict(),
                "correlation": {"n_events": c["n_events"], "n_clusters": c["n_clusters"],
                                "louvain_runtime_s": c["louvain_runtime_s"], "ari": c["ari"], "notes": c["notes"],
                                "qaoa": {k: v for k, v in c["qaoa"].items() if k not in ("labels", "subsample_ids")}}}

    @app.get("/incidents/{incident_id}/early-warning")
    def early_warning(incident_id: str):
        _incident_or_404(incident_id)
        return {"incident_id": incident_id, "alerts": pipeline.early_warning(incident_id, DB_PATH)}

    @app.get("/predictions")
    def predictions(minutes: int = 60, threshold: float = precursor.THRESHOLD):
        return {"alerts": [a.to_dict() for a in precursor.recent_predictions(_conn(), minutes, threshold)]}

    @app.get("/incidents/{incident_id}/rca")
    def rca(incident_id: str, refresh: bool = False):
        _incident_or_404(incident_id)
        return pipeline.rca_for_incident(incident_id, DB_PATH, refresh=refresh)["rca"]

    @app.get("/incidents/{incident_id}/actions")
    def actions(incident_id: str):
        _incident_or_404(incident_id)
        return pipeline.actions_for_incident(incident_id, DB_PATH)

    def _decide(decision: str):
        def handler(incident_id: str, action_id: str, operator: str = Body("operator", embed=True)):
            _incident_or_404(incident_id)
            try:
                return approval.decide(_conn(), incident_id, action_id, decision, operator)
            except KeyError:
                raise HTTPException(404, f"unknown action {action_id} for {incident_id}")
            except approval.StateError as exc:
                raise HTTPException(409, str(exc))
        return handler

    for d in ("approve", "reject", "escalate"):
        app.post(f"/incidents/{{incident_id}}/actions/{{action_id}}/{d}", name=d)(_decide(d))

    @app.get("/audit")
    def audit(incident_id: Optional[str] = None, limit: int = 200):
        return approval.audit_entries(_conn(), incident_id, limit)

    # Only exists if Phase 5.5 produced a real result; never a stub.
    if qsvm.load_result() is not None:
        @app.get("/predictions/quantum-vs-classical")
        def quantum_vs_classical():
            return qsvm.load_result()

    return app


def _jsonable(o):
    from datetime import datetime as _dt
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    return o.isoformat() if isinstance(o, _dt) else o


app = create_app()
