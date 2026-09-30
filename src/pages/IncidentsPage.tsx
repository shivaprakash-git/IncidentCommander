import React, { useState } from "react";
import { useIncidents } from "../context/IncidentContext";
import { IncidentRow } from "../components/Rows";
import { Loading, ErrorState } from "../components/States";
import { TIMEZONE_LABEL } from "../lib/format";
import { humanType } from "../lib/labels";
import type { Severity } from "../types";

export const IncidentsPage: React.FC = () => {
  const { incidents, loading, error, refresh } = useIncidents();
  const [query, setQuery] = useState("");
  const [severity, setSeverity] = useState<Severity | "all">("all");
  const [status, setStatus] = useState<"all" | "open" | "mitigating">("all");

  const q = query.trim().toLowerCase();
  const filtered = incidents.filter((inc) => {
    if (severity !== "all" && inc.trigger_severity !== severity) return false;
    if (status !== "all" && inc.status !== status) return false;
    return !q || [inc.incident_id, inc.type, humanType(inc.type), inc.description].some((v) => v.toLowerCase().includes(q));
  });

  return (
    <div className="page">
      <div className="page-header">
        <h4>Incidents</h4>
        <p className="text-2 mb-0">
          Incident windows discovered in the SUMLOG. Open one to see its timeline, cause and actions. Times are {TIMEZONE_LABEL}.
        </p>
      </div>

      <div className="d-flex flex-wrap gap-2 mb-3">
        <input
          id="incident-search"
          type="search"
          className="form-control form-control-sm"
          style={{ maxWidth: 280 }}
          placeholder="Search by ID, type or description"
          aria-label="Search incidents"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select
          id="incident-severity"
          className="form-select form-select-sm"
          style={{ maxWidth: 160 }}
          aria-label="Filter by severity"
          value={severity}
          onChange={(e) => setSeverity(e.target.value as Severity | "all")}
        >
          <option value="all">All severities</option>
          <option value="CRIT">Critical</option>
          <option value="WARN">Warning</option>
          <option value="INFO">Info</option>
        </select>
        <select
          id="incident-status"
          className="form-select form-select-sm"
          style={{ maxWidth: 160 }}
          aria-label="Filter by status"
          value={status}
          onChange={(e) => setStatus(e.target.value as "all" | "open" | "mitigating")}
        >
          <option value="all">All statuses</option>
          <option value="open">Open</option>
          <option value="mitigating">Mitigating</option>
        </select>
      </div>

      <div className="panel">
        {loading ? (
          <Loading />
        ) : error && incidents.length === 0 ? (
          <ErrorState error={error} onRetry={() => void refresh()} />
        ) : filtered.length === 0 ? (
          <div className="empty">{incidents.length === 0 ? "No incidents yet." : "No incidents match your filters."}</div>
        ) : (
          filtered.map((inc) => <IncidentRow key={inc.incident_id} incident={inc} />)
        )}
      </div>
    </div>
  );
};
