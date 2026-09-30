import React, { useState } from "react";
import { ModalShell } from "./ModalShell";

interface Props {
  patternId: string;
  onConfirm: (reason: string) => Promise<void>;
  onClose: () => void;
}

export const DismissReasonModal: React.FC<Props> = ({ patternId, onConfirm, onClose }) => {
  const [reason, setReason] = useState("");
  return (
    <ModalShell
      titleId="dismiss-title"
      title="Dismiss early warning?"
      submitLabel="Dismiss"
      submitClass="btn-danger"
      canSubmit={!!reason.trim()}
      onSubmit={() => onConfirm(reason.trim())}
      onClose={onClose}
    >
      <p className="text-2 mb-3" style={{ fontSize: "0.9rem" }}>
        <span className="font-mono">{patternId}</span> will be marked dismissed. Your reason is saved to the audit log.
      </p>
      <textarea
        id="dismiss-reason"
        className="form-control"
        rows={3}
        required
        autoFocus
        placeholder="e.g. Planned maintenance window"
        aria-label="Reason for dismissal"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
      />
    </ModalShell>
  );
};
