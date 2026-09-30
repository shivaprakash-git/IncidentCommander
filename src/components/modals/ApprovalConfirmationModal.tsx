import React, { useState } from "react";
import type { ActionRow } from "../../types";
import { RiskBadge } from "../RiskBadge";
import { ModalShell } from "./ModalShell";

interface Props {
  action: ActionRow;
  onConfirm: (note?: string) => Promise<void>;
  onClose: () => void;
}

export const ApprovalConfirmationModal: React.FC<Props> = ({ action, onConfirm, onClose }) => {
  const [note, setNote] = useState("");
  return (
    <ModalShell
      titleId="approve-title"
      title="Approve action"
      submitLabel="Confirm approval"
      onSubmit={() => onConfirm(note.trim() || undefined)}
      onClose={onClose}
    >
      <dl className="row mb-3" style={{ fontSize: "0.9rem" }}>
        <dt className="col-4 small-label fw-normal">Action</dt>
        <dd className="col-8 fw-medium">{action.title}</dd>
        <dt className="col-4 small-label fw-normal">Risk tier</dt>
        <dd className="col-8"><RiskBadge level={action.risk_level} /></dd>
        <dt className="col-4 small-label fw-normal">Rule</dt>
        <dd className="col-8 font-mono" style={{ fontSize: "0.82rem" }}>action_catalog.yaml#{action.action_id}</dd>
        <dt className="col-4 small-label fw-normal">Because</dt>
        <dd className="col-8 text-2">{action.hypothesis_cause} ({Math.round(action.confidence * 100)}%)</dd>
        <dt className="col-4 small-label fw-normal">Evidence</dt>
        <dd className="col-8 mb-0">
          {action.evidence_event_ids.length === 0 ? (
            <span className="text-3">None cited</span>
          ) : (
            <div className="d-flex flex-wrap gap-1">
              {action.evidence_event_ids.map((id) => (
                <span key={id} className="pill pill-neutral font-mono">{id}</span>
              ))}
            </div>
          )}
        </dd>
      </dl>
      <textarea
        id="approve-note"
        className="form-control"
        rows={2}
        placeholder="Operator note (optional, saved to the audit log)"
        aria-label="Operator note"
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
    </ModalShell>
  );
};
