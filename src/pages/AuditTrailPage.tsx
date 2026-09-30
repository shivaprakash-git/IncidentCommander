import React, { useState } from "react";
import { Link } from "react-router-dom";
import { useIncidents } from "../context/IncidentContext";
import { DecisionBadge, DECISION_LABELS } from "../components/DecisionBadge";
import { RiskBadge } from "../components/RiskBadge";
import { Loading, ErrorState } from "../components/States";
import { formatDateTime } from "../lib/format";
import type { AuditEntry } from "../types";
import { describeAudit, str } from "../lib/audit";

const RANGES: { value: string; label: string; minutes: number | null }[] = [
  { value: "1h", label: "Last hour", minutes: 60 },
  { value: "24h", label: "Last 24 hours", minutes: 1440 },
  { value: "7d", label: "Last 7 days", minutes: 10080 },
  { value: "all", label: "All time", minutes: null },
];

const noteOf = (e: AuditEntry) => str(e.evidence_shown.note) || str(e.evidence_shown.reason);
const evidenceOf = (e: AuditEntry): string[] => {
  const ids = e.evidence_shown.evidence_event_ids;
  return Array.isArray(ids) ? ids.map(String) : [];
};

export const AuditTrailPage: React.FC = () => {
  const { audit, catalog, loading, error, refresh } = useIncidents();
  const [query, setQuery] = useState("");
  const [decision, setDecision] = useState("all");
  const [range, setRange] = useState("all");

  const q = query.trim().toLowerCase();
  const minutes = RANGES.find((r) => r.value === range)?.minutes ?? null;
  const now = Date.now();
  const filtered = audit.filter((e) => {
    if (decision !== "all" && e.decision !== decision) return false;
    if (minutes !== null && now - new Date(e.timestamp).getTime() > minutes * 60_000) return false;
    if (!q) return true;
    return [String(e.id), e.incident_id ?? "", e.action_id ?? "", e.operator, describeAudit(e, catalog), noteOf(e), ...evidenceOf(e)].some((v) =>
      v.toLowerCase().includes(q)
    );
  });

  return (
    <div className="page">
      <div className="page-header">
        <h4>Audit log</h4>
        <p className="text-2 mb-0">
          Every decision, who made it, and the evidence behind it. Append-only (the database refuses edits and deletes),
          newest first.
        </p>
      </div>

      <div className="d-flex flex-wrap gap-2 mb-3">
        <input
          id="audit-search"
          type="search"
          className="form-control form-control-sm"
          style={{ maxWidth: 280 }}
          placeholder="Search incident, operator, event ID"
          aria-label="Search audit log"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select
          id="audit-decision"
          className="form-select form-select-sm"
          style={{ maxWidth: 190 }}
          aria-label="Filter by decision"
          value={decision}
          onChange={(e) => setDecision(e.target.value)}
        >
          <option value="all">All decisions</option>
          {Object.entries(DECISION_LABELS).map(([d, { text }]) => (
            <option key={d} value={d}>{text}</option>
          ))}
        </select>
        <select
          id="audit-range"
          className="form-select form-select-sm"
          style={{ maxWidth: 160 }}
          aria-label="Filter by time range"
          value={range}
          onChange={(e) => setRange(e.target.value)}
        >
          {RANGES.map((r) => (
            <option key={r.value} value={r.value}>{r.label}</option>
          ))}
        </select>
      </div>

      <div className="panel overflow-hidden">
        {loading ? (
          <Loading />
        ) : error && audit.length === 0 ? (
          <ErrorState error={error} onRetry={() => void refresh()} />
        ) : filtered.length === 0 ? (
          <div className="empty">{audit.length === 0 ? "No audit entries yet." : "No entries match."}</div>
        ) : (
          <div className="table-responsive">
            <table className="table audit-table m-0">
              <thead>
                <tr>
                  <th className="ps-4">Seq</th>
                  <th>Time</th>
                  <th>Operator</th>
                  <th>Action</th>
                  <th>Decision</th>
                  <th>Risk tier</th>
                  <th className="pe-4">Evidence shown</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((e) => {
                  const note = noteOf(e);
                  const evidence = evidenceOf(e);
                  return (
                    <tr key={e.id}>
                      <td className="ps-4 font-mono text-3">#{e.id}</td>
                      <td className="font-mono text-nowrap text-2">{formatDateTime(e.timestamp)}</td>
                      <td className="font-mono text-nowrap">{e.operator}</td>
                      <td style={{ minWidth: 220 }}>
                        <div className="fw-medium">{describeAudit(e, catalog)}</div>
                        {note && <div className="text-2" style={{ fontSize: "0.82rem" }}>{note}</div>}
                        {e.incident_id && (
                          <Link to={`/incidents/${e.incident_id}/timeline`} className="small font-mono">{e.incident_id}</Link>
                        )}
                        {e.action_id && <span className="small-label font-mono ms-2">{e.action_id}</span>}
                      </td>
                      <td><DecisionBadge decision={e.decision} /></td>
                      <td>{e.risk_level ? <RiskBadge level={e.risk_level} /> : <span className="text-3">—</span>}</td>
                      <td className="pe-4">
                        {evidence.length === 0 ? (
                          <span className="text-3">—</span>
                        ) : (
                          <div className="d-flex flex-wrap gap-1">
                            {evidence.slice(0, 6).map((id) =>
                              e.incident_id ? (
                                <Link
                                  key={id}
                                  to={`/incidents/${e.incident_id}/timeline?event=${encodeURIComponent(id)}`}
                                  className="pill pill-neutral font-mono text-decoration-none"
                                >
                                  {id}
                                </Link>
                              ) : (
                                <span key={id} className="pill pill-neutral font-mono">{id}</span>
                              )
                            )}
                            {evidence.length > 6 && <span className="small-label">+{evidence.length - 6}</span>}
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
