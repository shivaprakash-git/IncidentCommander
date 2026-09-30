import React from "react";

export const Loading: React.FC<{ label?: string; className?: string }> = ({ label = "Loading…", className = "" }) => (
  <div className={`empty d-flex align-items-center justify-content-center gap-2 ${className}`} role="status">
    <span className="spinner-border spinner-border-sm text-3" aria-hidden="true"></span>
    <span>{label}</span>
  </div>
);

export const ErrorState: React.FC<{ error: Error; onRetry?: () => void; className?: string }> = ({
  error,
  onRetry,
  className = "",
}) => (
  <div className={`empty ${className}`} role="alert">
    <i className="bi bi-exclamation-triangle fs-4 d-block mb-2" style={{ color: "var(--uc-critical)" }}></i>
    <div className="mb-3">{error.message}</div>
    {onRetry && (
      <button type="button" className="btn btn-sm btn-outline-primary" onClick={onRetry}>
        Try again
      </button>
    )}
  </div>
);
