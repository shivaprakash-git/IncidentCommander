import React from "react";
import type { Severity } from "../types";
import { SEVERITY_LABEL } from "../lib/labels";

const CLS: Record<Severity, string> = { CRIT: "pill-critical", WARN: "pill-warning", INFO: "pill-info" };

export const SeverityBadge: React.FC<{ severity: Severity | null | undefined }> = ({ severity }) =>
  severity ? (
    <span className={`pill ${CLS[severity]}`}>{SEVERITY_LABEL[severity]}</span>
  ) : (
    <span className="pill pill-neutral">Unknown</span>
  );
