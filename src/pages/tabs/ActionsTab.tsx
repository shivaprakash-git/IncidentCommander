import React, { useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import type { ActionRow, ActionStatus } from "../../types";
import { api } from "../../api";
import { useIncidents } from "../../context/IncidentContext";
import { RiskBadge } from "../../components/RiskBadge";
import { Loading, ErrorState } from "../../components/States";
import { ApprovalConfirmationModal } from "../../components/modals/ApprovalConfirmationModal";
import { EscalateModal } from "../../components/modals/EscalateModal";
import { ConfirmModal } from "../../components/modals/ConfirmModal";
import { useApi } from "../../lib/format";
import type { IncidentOutlet } from "../IncidentDetailPage";

const STATUS_PILL: Record<Exclude<ActionStatus, "pending">, { cls: string; text: string }> = {
  auto_approved: { cls: "pill-info", text: "Auto · Safe" },
  approved: { cls: "pill-safe", text: "Approved" },
  rejected: { cls: "pill-critical", text: "Rejected" },
  escalated: { cls: "pill-warning", text: "Escalated" },
};

export const ActionsTab: React.FC = () => {
  const { incident, reloadIncident } = useOutletContext<IncidentOutlet>();
  const { decide } = useIncidents();
  const hasActions = Object.keys(incident.actions_by_status).length > 0;
  // Recommending actions needs the RCA; only auto-load when that won't trigger a long LLM call.
  const canLoad = incident.rca_cached || hasActions;
  const actions = useApi(() => api.incidentActions(incident.incident_id), [incident.incident_id], { enabled: canLoad });
  const [approving, setApproving] = useState<ActionRow | null>(null);
  const [escalating, setEscalating] = useState<ActionRow | null>(null);
  const [rejecting, setRejecting] = useState<ActionRow | null>(null);

  const apply = async (row: ActionRow, decision: "approve" | "reject" | "escalate", note?: string) => {
    await decide(row.incident_id, row.action_id, decision, note);
    await actions.reload();
    void reloadIncident();
  };

  if (!canLoad) {
    return (
      <div className="panel panel-pad text-center py-5">
        <i className="bi bi-shield-check fs-3 text-3 d-block mb-2"></i>
        <h6 className="mb-1">Actions come from the root cause analysis</h6>
        <p className="text-2 mb-3" style={{ fontSize: "0.9rem" }}>
          Run the root cause analysis first; matching actions are then taken from the action catalog with their risk tiers.
        </p>
        <Link to={`/incidents/${incident.incident_id}/rca`} className="btn btn-primary">Go to root cause</Link>
      </div>
    );
  }
  if (actions.loading) return <div className="panel"><Loading label="Loading recommended actions…" /></div>;
  if (actions.error || !actions.data) {
    return <div className="panel"><ErrorState error={actions.error ?? new Error("No actions")} onRetry={() => void actions.reload()} /></div>;
  }

  return (
    <>
      <div className="panel">
        {actions.data.length === 0 && <div className="empty">No actions recommended for this incident.</div>}
        {actions.data.map((act) => {
          const status = act.status !== "pending" ? STATUS_PILL[act.status] : null;
          return (
            <div key={act.action_id} className="list-row d-flex flex-column flex-md-row align-items-md-center gap-3">
              <div className="flex-grow-1 min-w-0">
                <div className="d-flex flex-wrap align-items-center gap-2 mb-1">
                  <RiskBadge level={act.risk_level} />
                  <span className="small-label font-mono">{act.action_id}</span>
                  <span className="small-label">{act.subsystem}</span>
                </div>
                <div className="fw-medium">{act.title}</div>
                <div className="text-2" style={{ fontSize: "0.88rem" }}>{act.description}</div>
                <div className="small-label mt-1">
                  For: {act.hypothesis_cause}
                  {act.confidence > 0 && ` (${Math.round(act.confidence * 100)}%)`}
                </div>
              </div>

              <div className="flex-shrink-0 d-flex align-items-center gap-2">
                {status ? (
                  <span className={`pill ${status.cls}`}>{status.text}</span>
                ) : act.risk_level === "needs_approval" ? (
                  <>
                    <button type="button" className="btn btn-sm btn-light" onClick={() => setRejecting(act)}>Reject</button>
                    <button type="button" className="btn btn-sm btn-primary" onClick={() => setApproving(act)}>Approve</button>
                  </>
                ) : act.risk_level === "forbidden" ? (
                  <button type="button" className="btn btn-sm btn-outline-warning" onClick={() => setEscalating(act)}>
                    Escalate
                  </button>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>
      <p className="small-label mt-2 mb-0">
        <i className="bi bi-shield-lock me-1"></i>
        Risk tiers come from <span className="font-mono">action_catalog.yaml</span>, never the LLM. Safe actions are
        informational and auto-approved; every decision is written to the audit log.
      </p>

      {approving && (
        <ApprovalConfirmationModal
          action={approving}
          onConfirm={async (note) => {
            await apply(approving, "approve", note);
            setApproving(null);
          }}
          onClose={() => setApproving(null)}
        />
      )}
      {escalating && (
        <EscalateModal
          action={escalating}
          onConfirm={async (note) => {
            await apply(escalating, "escalate", note);
            setEscalating(null);
          }}
          onClose={() => setEscalating(null)}
        />
      )}
      {rejecting && (
        <ConfirmModal
          title="Reject this action?"
          confirmLabel="Reject"
          confirmClass="btn-danger"
          body={<><strong>{rejecting.title}</strong> will be marked rejected and logged. Decisions are final.</>}
          onConfirm={async () => {
            await apply(rejecting, "reject");
            setRejecting(null);
          }}
          onClose={() => setRejecting(null)}
        />
      )}
    </>
  );
};
