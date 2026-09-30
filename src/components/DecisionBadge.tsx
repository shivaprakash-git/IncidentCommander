import React from "react";

// Backend audit decision values (docs/BACKEND_API.md, audit section).
export const DECISION_LABELS: Record<string, { cls: string; text: string }> = {
  "auto-approved": { cls: "pill-info", text: "Auto · Safe" },
  approved: { cls: "pill-safe", text: "Approved" },
  rejected: { cls: "pill-critical", text: "Rejected" },
  escalated: { cls: "pill-warning", text: "Escalated" },
  warning_dismissed: { cls: "pill-neutral", text: "Warning dismissed" },
  opened_as_incident: { cls: "pill-predict", text: "Opened as incident" },
  log_uploaded: { cls: "pill-info", text: "Log uploaded" },
  ingest: { cls: "pill-neutral", text: "System" },
};

export const DecisionBadge: React.FC<{ decision: string }> = ({ decision }) => {
  const { cls, text } = DECISION_LABELS[decision] ?? { cls: "pill-neutral", text: decision };
  return <span className={`pill ${cls}`}>{text}</span>;
};
