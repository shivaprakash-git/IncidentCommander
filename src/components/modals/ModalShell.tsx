import React, { useState } from "react";

interface Props {
  titleId: string;
  title: string;
  children: React.ReactNode;
  submitLabel: string;
  submitClass?: string;
  canSubmit?: boolean;
  onSubmit: () => Promise<void>;
  onClose: () => void;
}

// Dialog frame with an async submit: shows a busy state and the backend's error message on failure.
export const ModalShell: React.FC<Props> = ({
  titleId,
  title,
  children,
  submitLabel,
  submitClass = "btn-primary",
  canSubmit = true,
  onSubmit,
  onClose,
}) => {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit || busy) return;
    setBusy(true);
    setError(null);
    try {
      await onSubmit();
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop-min" onClick={busy ? undefined : onClose}>
      <form
        className="modal-min"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onSubmit={submit}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-4">
          <h5 id={titleId} className="mb-3">{title}</h5>
          {children}
          {error && (
            <div className="text-danger mt-3" role="alert" style={{ fontSize: "0.88rem" }}>
              <i className="bi bi-exclamation-triangle me-1"></i>
              {error}
            </div>
          )}
        </div>
        <div className="d-flex justify-content-end gap-2 px-4 pb-4">
          <button type="button" className="btn btn-light" disabled={busy} onClick={onClose}>Cancel</button>
          <button type="submit" className={`btn ${submitClass}`} disabled={!canSubmit || busy}>
            {busy && <span className="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>}
            {submitLabel}
          </button>
        </div>
      </form>
    </div>
  );
};
