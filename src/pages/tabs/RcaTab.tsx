import React, { useRef } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { api } from "../../api";
import { Loading, ErrorState } from "../../components/States";
import { useApi, useElapsed } from "../../lib/format";
import type { IncidentOutlet } from "../IncidentDetailPage";

export const RcaTab: React.FC = () => {
  const { incident, reloadIncident } = useOutletContext<IncidentOutlet>();
  // Only auto-load when a cached result exists; otherwise the operator starts the (slow) LLM call.
  const forceRefresh = useRef(false);
  const rca = useApi(
    () => {
      const refresh = forceRefresh.current;
      forceRefresh.current = false;
      return api.rca(incident.incident_id, refresh);
    },
    [incident.incident_id],
    { enabled: incident.rca_cached }
  );
  const elapsed = useElapsed(rca.loading);

  const run = async (refresh = false) => {
    forceRefresh.current = refresh;
    if (await rca.reload()) void reloadIncident();
  };

  if (!rca.data && !rca.loading && !rca.error) {
    return (
      <div className="panel panel-pad text-center py-5">
        <i className="bi bi-search fs-3 text-3 d-block mb-2"></i>
        <h6 className="mb-1">No root cause analysis yet</h6>
        <p className="text-2 mb-3 mx-auto" style={{ maxWidth: 520, fontSize: "0.9rem" }}>
          The RCA agent retrieves matching runbooks and past incidents, then asks the LLM for cited hypotheses. On the
          hosted model this can take several minutes. The result is cached afterwards.
        </p>
        <button type="button" className="btn btn-primary" onClick={() => void run()}>
          Run root cause analysis
        </button>
      </div>
    );
  }

  if (rca.loading) {
    return (
      <div className="panel">
        <Loading
          label={
            incident.rca_cached && !forceRefresh.current
              ? "Loading root cause analysis…"
              : `Running root cause analysis… ${elapsed}s (can take several minutes)`
          }
        />
      </div>
    );
  }
  if (rca.error || !rca.data) {
    return <div className="panel"><ErrorState error={rca.error ?? new Error("No result")} onRetry={() => void run()} /></div>;
  }

  const r = rca.data;
  const sorted = [...r.hypotheses].sort((a, b) => b.confidence - a.confidence);

  return (
    <div className="d-flex flex-column gap-3">
      {r.transient && (
        <div className="panel panel-pad d-flex flex-wrap align-items-center gap-3">
          <i className="bi bi-cloud-slash fs-5" style={{ color: "var(--uc-warning)" }}></i>
          <div className="flex-grow-1" style={{ fontSize: "0.9rem" }}>
            The LLM was unavailable, so no hypothesis was produced. This outage was not cached.
            {r.reason && <div className="small-label">{r.reason}</div>}
          </div>
          <button type="button" className="btn btn-sm btn-outline-primary" onClick={() => void run(true)}>Try again</button>
        </div>
      )}

      {r.insufficient_evidence && !r.transient && (
        <div className="panel panel-pad" style={{ borderColor: "var(--uc-warning)" }}>
          <span className="pill pill-warning mb-2">Insufficient evidence</span>
          <p className="mb-1">The system will not guess a root cause for this incident.</p>
          {r.reason && <p className="small-label mb-0">{r.reason}</p>}
        </div>
      )}

      {sorted.map((h, idx) => {
        const pct = Math.round(h.confidence * 100);
        const weak = h.confidence < 0.5;
        return (
          <div key={idx} className="panel panel-pad" style={idx === 0 && !weak ? { borderColor: "var(--uc-safe)" } : undefined}>
            <div className="d-flex align-items-center justify-content-between gap-2 mb-2">
              <div className="d-flex align-items-center gap-2">
                <span className="small-label">#{idx + 1}</span>
                {idx === 0 && !weak && <span className="pill pill-safe">Most likely</span>}
                {weak && <span className="pill pill-warning">Low confidence</span>}
              </div>
              <div className="d-flex align-items-center gap-2">
                <div className="progress" style={{ width: 80, height: 6 }}>
                  <div className="progress-bar" style={{ width: `${pct}%`, background: weak ? "var(--uc-warning)" : "var(--uc-teal)" }}></div>
                </div>
                <span className="small-label font-mono">{pct}%</span>
              </div>
            </div>
            <p className="mb-2">{h.cause}</p>
            <div className="d-flex flex-wrap gap-1">
              {h.evidence_event_ids.map((e) => (
                <Link key={e} to={`/incidents/${incident.incident_id}/timeline?event=${e}`} className="pill pill-neutral font-mono text-decoration-none">
                  {e}
                </Link>
              ))}
              {h.runbook_refs.map((ref) => (
                <span key={ref} className="pill pill-info">
                  <i className="bi bi-book"></i>
                  {ref}
                </span>
              ))}
            </div>
          </div>
        );
      })}

      {r.retrieved && r.retrieved.length > 0 && (
        <div className="panel">
          <div className="panel-head"><h6 className="m-0">Retrieved context</h6><span className="small-label">similarity</span></div>
          {r.retrieved.map((c) => (
            <div key={c.chunk_id} className="list-row d-flex justify-content-between gap-3" style={{ fontSize: "0.88rem" }}>
              <span className="min-w-0 text-truncate">
                <span className="font-mono">{c.chunk_id}</span> <span className="text-3">· {c.source}</span>
              </span>
              <span className="font-mono text-2">{c.score.toFixed(3)}</span>
            </div>
          ))}
        </div>
      )}

      <div className="d-flex flex-wrap justify-content-between align-items-center gap-2">
        <p className="small-label mb-0">
          Hypotheses are LLM suggestions with cited events and runbooks
          {r.dropped_references ? ` (${r.dropped_references} uncited references dropped)` : ""}. Risk decisions happen in Actions.
        </p>
        <Link to={`/incidents/${incident.incident_id}/actions`} className="btn btn-outline-primary btn-sm">
          Next: see actions <i className="bi bi-arrow-up-right ms-1"></i>
        </Link>
      </div>
    </div>
  );
};
