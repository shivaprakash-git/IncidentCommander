import React, { useState } from "react";
import type { ActionRow } from "../../types";
import { ModalShell } from "./ModalShell";

interface Props {
  action: ActionRow;
  onConfirm: (note?: string) => Promise<void>;
  onClose: () => void;
}

export const EscalateModal: React.FC<Props> = ({ action, onConfirm, onClose }) => {
  const [note, setNote] = useState("");
  return (
    <ModalShell
      titleId="escalate-title"
      title="Escalate to operations lead"
      submitLabel="Escalate"
      submitClass="btn-warning text-white"
      onSubmit={() => onConfirm(note.trim() || undefined)}
      onClose={onClose}
    >
      <p className="text-2 mb-3" style={{ fontSize: "0.9rem" }}>
        <strong>{action.title}</strong> is forbidden by the action catalog
        (<span className="font-mono">{action.action_id}</span>) and cannot be executed from here. Escalating records the
        request in the audit log.
      </p>
      <textarea
        id="escalate-note"
        className="form-control"
        rows={2}
        placeholder="Context for the lead (optional)"
        aria-label="Escalation note"
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
    </ModalShell>
  );
};
