import React from "react";
import { useParams, Link, NavLink, Outlet } from "react-router-dom";
import { api, ApiError } from "../api";
import { useIncidents } from "../context/IncidentContext";
import { SeverityBadge } from "../components/SeverityBadge";
import { StatusChip } from "../components/Rows";
import { Loading, ErrorState } from "../components/States";
import { TIMEZONE_LABEL, formatDuration, formatSpan, secondsBetween, useApi } from "../lib/format";
import { SOURCE_LABEL, humanType } from "../lib/labels";
import type { IncidentDetail } from "../types";

export interface IncidentOutlet {
  incident: IncidentDetail;
  reloadIncident: () => Promise<unknown>;
}

export const IncidentDetailPage: React.FC = () => {
  const { id = "" } = useParams<{ id: string }>();
  const { incidents } = useIncidents();
  const { data: incident, error, loading, reload } = useApi(() => api.incident(id), [id]);
  const row = incidents.find((i) => i.incident_id === id);

  const back = (
    <Link to="/incidents" className="back-link">
      <i className="bi bi-arrow-left"></i> Incidents
    </Link>
  );

  if (loading && !incident) return <div className="page">{back}<Loading /></div>;
  if (error || !incident) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <div className="page">
        {back}
        {notFound ? (
          <div className="empty">
            <h5>Incident {id} not found</h5>
            <p className="mb-0">It may have been cleared by a re-ingest.</p>
          </div>
        ) : (
          <ErrorState error={error ?? new Error("Unknown error")} onRetry={() => void reload()} />
        )}
      </div>
    );
  }

  const pending = row?.pending_approvals ?? 0;
  const tabs = [
    { to: "timeline", label: "Timeline" },
    { to: "rca", label: "Root cause" },
    { to: "actions", label: pending ? `Actions (${pending})` : "Actions" },
    { to: "comparison", label: "Quantum vs classical" },
  ];

  return (
    <div className="page">
      {back}

      <div className="d-flex flex-wrap align-items-center gap-2 mb-1">
        <SeverityBadge severity={row?.trigger_severity} />
        {row && <StatusChip status={row.status} />}
        <span className="font-mono small-label">{incident.incident_id}</span>
        <span className="pill pill-neutral">{SOURCE_LABEL[incident.source] ?? incident.source}</span>
        {incident.demo && <span className="pill pill-info">Demo</span>}
      </div>
      <h4 className="mb-1">{humanType(incident.type)}</h4>
      <p className="text-2 mb-1" style={{ fontSize: "0.92rem" }}>{incident.description}</p>
      <p className="small-label mb-4">
        {formatSpan(incident.window_start, incident.window_end)} {TIMEZONE_LABEL} ·{" "}
        {formatDuration(secondsBetween(incident.window_start, incident.window_end))} window ·{" "}
        {incident.event_count.toLocaleString()} events · trigger <span className="font-mono">{incident.trigger_event_id}</span>
        {incident.keywords.length > 0 && <> · {incident.keywords.join(", ")}</>}
      </p>

      <nav className="tabs mb-4">
        {tabs.map((t) => (
          <NavLink key={t.to} to={t.to}>{t.label}</NavLink>
        ))}
      </nav>

      <Outlet context={{ incident, reloadIncident: reload } satisfies IncidentOutlet} />
    </div>
  );
};
