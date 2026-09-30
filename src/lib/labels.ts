import type { RiskLevel, Severity } from "../types";

// Placeholder operator identity (the backend has no auth yet). Sent with every decision and shown in the sidebar.
export const CURRENT_OPERATOR = { id: "OP_SGURUPR", role: "MCP Operations" };

const TYPE_LABELS: Record<string, string> = {
  auth_failure_security_violation: "Authentication failure / security violation",
  auth_failure_security_violation_halt: "Authentication failure with halt/load",
  linkage_failure: "Linkage failure (missing code file)",
  db_lock_contention_cascade: "DMSII lock contention cascade",
  disk_capacity_file_open_failures: "Disk capacity: file open failures",
  halt_load: "Halt/load",
  task_abend: "Task abend",
  sumlog_discard: "SUMLOG entries discarded",
  operation_failed: "Operation failed",
};

export const humanType = (type: string) =>
  TYPE_LABELS[type] ?? type.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

export const SEVERITY_LABEL: Record<Severity, string> = { CRIT: "Critical", WARN: "Warning", INFO: "Info" };

export const RISK_LABEL: Record<RiskLevel, string> = {
  safe: "Safe",
  needs_approval: "Needs approval",
  forbidden: "Forbidden",
};

export const SOURCE_LABEL: Record<string, string> = {
  real: "SUMLOG",
  synthetic: "Synthetic",
  prediction: "From early warning",
  upload: "Uploaded log",
};

export const humanFeature = (name: string) => name.replace(/_/g, " ");
