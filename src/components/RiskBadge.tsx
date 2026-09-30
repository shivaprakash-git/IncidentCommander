import React from "react";
import type { RiskLevel } from "../types";
import { RISK_LABEL } from "../lib/labels";

const CONFIG: Record<RiskLevel, { cls: string; icon: string }> = {
  safe: { cls: "pill-safe", icon: "bi-check-circle" },
  needs_approval: { cls: "pill-warning", icon: "bi-exclamation-circle" },
  forbidden: { cls: "pill-critical", icon: "bi-x-octagon" },
};

export const RiskBadge: React.FC<{ level: RiskLevel }> = ({ level }) => {
  const { cls, icon } = CONFIG[level];
  return (
    <span className={`pill ${cls}`} title="Risk level set by action_catalog.yaml (rule engine)">
      <i className={`bi ${icon}`} aria-hidden="true"></i>
      {RISK_LABEL[level]}
    </span>
  );
};
