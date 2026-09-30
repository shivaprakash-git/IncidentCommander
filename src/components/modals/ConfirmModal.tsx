import React from "react";
import { ModalShell } from "./ModalShell";

interface Props {
  title: string;
  body: React.ReactNode;
  confirmLabel: string;
  confirmClass?: string;
  onConfirm: () => Promise<void>;
  onClose: () => void;
}

export const ConfirmModal: React.FC<Props> = ({ title, body, confirmLabel, confirmClass, onConfirm, onClose }) => (
  <ModalShell
    titleId="confirm-title"
    title={title}
    submitLabel={confirmLabel}
    submitClass={confirmClass}
    onSubmit={onConfirm}
    onClose={onClose}
  >
    <div className="text-2" style={{ fontSize: "0.9rem" }}>{body}</div>
  </ModalShell>
);
