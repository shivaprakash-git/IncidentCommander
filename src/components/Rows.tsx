import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { IncidentRow as Incident, IncidentStatus, Prediction } from "../types";
import { SeverityBadge } from "./SeverityBadge";
import { DismissReasonModal } from "./modals/DismissReasonModal";
import { useIncidents } from "../context/IncidentContext";
import { formatDuration, formatSpan, secondsBetween } from "../lib/format";
import { SOURCE_LABEL, humanType } from "../lib/labels";

const STATUS_LABEL: Record<IncidentStatus, string> = { open: "Open", mitigating: "Mitigating" };

export const StatusChip: React.FC<{ status: IncidentStatus }> = ({ status }) => (
  <span className={`status-chip status-${status}`}>{STATUS_LABEL[status]}</span>
);

export const IncidentRow: React.FC<{ incident: Incident; compact?: boolean }> = ({ incident: inc, compact }) => {
  const span = `${formatSpan(inc.window_start, inc.window_end)} · ${formatDuration(secondsBetween(inc.window_start, inc.window_end))}`;
  const title = humanType(inc.type);
  return (
    <Link to={`/incidents/${inc.incident_id}/timeline`} className="row-link">
      <SeverityBadge severity={inc.trigger_severity} />
      <div className="flex-grow-1 min-w-0">
        <div className="fw-medium text-truncate" title={`${title} — ${inc.description}`}>{title}</div>
        <div className="small-label d-flex flex-wrap column-gap-2">
          <span className="font-mono">{inc.incident_id}</span>
          <StatusChip status={inc.status} />
          {inc.pending_approvals > 0 && <span className="text-warning fw-medium">{inc.pending_approvals} awaiting approval</span>}
          {inc.pending_escalations > 0 && <span className="text-danger fw-medium">{inc.pending_escalations} to escalate</span>}
          {inc.source !== "real" && <span>{SOURCE_LABEL[inc.source] ?? inc.source}</span>}
          <span className={compact ? "" : "d-md-none"}>{span}</span>
        </div>
        {!compact && <div className="small-label text-truncate" title={inc.description}>{inc.description}</div>}
      </div>
      {!compact && <div className="small-label text-end d-none d-md-block flex-shrink-0">{span}</div>}
      <i className="bi bi-chevron-right text-3 flex-shrink-0"></i>
    </Link>
  );
};

export const predictionTitle = (p: Prediction) =>
  `${humanType(p.matched_incident_type)} pattern${p.matched_incident_id ? ` (like ${p.matched_incident_id})` : ""}`;

export const PredictionRow: React.FC<{ prediction: Prediction; showActions?: boolean }> = ({ prediction: p, showActions = true }) => {
  const { openPrediction, dismissPrediction } = useIncidents();
  const navigate = useNavigate();
  const [dismissing, setDismissing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const decided = p.status !== "active";

  const open = async () => {
    setBusy(true);
    setError(null);
    try {
      navigate(`/incidents/${await openPrediction(p.alert_id)}/timeline`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };

  return (
    <div className={`list-row d-flex flex-column flex-md-row align-items-md-center gap-2 gap-md-3${decided ? " row-muted" : ""}`}>
      <div className="d-flex align-items-center gap-3 flex-grow-1 min-w-0">
        <i className="bi bi-graph-up-arrow fs-5 text-predict flex-shrink-0"></i>
        <div className="min-w-0">
          <Link
            to={`/predictor/${p.alert_id}`}
            className="fw-medium text-truncate d-block text-decoration-none"
            title={predictionTitle(p)}
            style={{ color: "inherit" }}
          >
            {predictionTitle(p)}
          </Link>
          <div className="small-label d-flex flex-wrap column-gap-2">
            <span className="font-mono">{p.alert_id}</span>
            <span>{p.subsystem}</span>
            <span>Matched window {formatSpan(p.window_start, p.window_end)}</span>
            <span className="font-mono text-predict">Similarity {p.similarity_score.toFixed(2)}</span>
          </div>
          {error && <div className="text-danger small mt-1">{error}</div>}
        </div>
      </div>
      {showActions && !decided && (
        <div className="d-flex gap-2 flex-shrink-0 ps-5 ps-md-0">
          <button type="button" className="btn btn-sm btn-light" disabled={busy} onClick={() => setDismissing(true)}>
            Dismiss
          </button>
          <button type="button" className="btn btn-sm btn-outline-primary" disabled={busy} onClick={open}>
            {busy ? "Opening…" : "Open as incident"}
          </button>
        </div>
      )}
      {decided && (
        <div className="flex-shrink-0 ps-5 ps-md-0 d-flex align-items-center gap-2">
          <span className={`pill ${p.status === "opened" ? "pill-predict" : "pill-neutral"}`}>
            {p.status === "opened" ? "Opened" : "Dismissed"}
          </span>
          {p.incident_id && (
            <Link to={`/incidents/${p.incident_id}/timeline`} className="small font-mono">{p.incident_id}</Link>
          )}
        </div>
      )}
      {dismissing && (
        <DismissReasonModal
          patternId={p.alert_id}
          onConfirm={async (reason) => {
            await dismissPrediction(p.alert_id, reason);
            setDismissing(false);
          }}
          onClose={() => setDismissing(false)}
        />
      )}
    </div>
  );
};
