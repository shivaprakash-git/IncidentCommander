import type { AuditEntry, CatalogEntry } from "../types";

export const str = (v: unknown) => (v === undefined || v === null ? "" : String(v));

export function describeAudit(e: AuditEntry, catalog: Record<string, CatalogEntry>): string {
  const ev = e.evidence_shown;
  switch (e.decision) {
    case "warning_dismissed":
      return `Dismissed early warning ${str(ev.alert_id)}`;
    case "opened_as_incident":
      return `Opened early warning ${str(ev.alert_id)} as ${str(e.incident_id)}`;
    case "log_uploaded":
      return `Uploaded SUMLOG ${str(ev.filename)} (${str(ev.records)} records${ev.host ? ` from ${str(ev.host)}` : ""})`;
    case "ingest":
      return `Ingest run: ${str(ev.events_total)} events (${str(ev.source)})`;
    default:
      return e.action_id ? catalog[e.action_id]?.title ?? e.action_id : e.decision;
  }
}

