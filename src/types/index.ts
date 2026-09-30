// Shapes returned by the FastAPI backend (docs/BACKEND_API.md). Field names match the API.

export type Severity = "CRIT" | "WARN" | "INFO";
export type RiskLevel = "safe" | "needs_approval" | "forbidden";
export type ActionStatus = "pending" | "auto_approved" | "approved" | "rejected" | "escalated";
export type IncidentStatus = "open" | "mitigating";
export type TimelineRole = "trigger" | "propagation" | "symptom";
export type Decision = "approve" | "reject" | "escalate";

export interface Health {
  status: string;
  events: number;
  incidents: number;
  data_file_present: boolean;
  nim_chat_key_set: boolean;
  nim_embed_key_set: boolean;
  qsvm_result: boolean;
  last_ingest_at: string | null;
  rule_engine_version: string;
  llm_configured: boolean;
  quantum_solver: "idle" | "running";
}

export interface Summary {
  events_total: number;
  events_by_severity: Record<string, number>;
  alerts: number;
  incidents: number;
  demo_incidents: number;
  headline: string;
  incidents_by_type: Record<string, number>;
  actions_by_status: Record<string, number>;
  pending_approvals: number;
  audit_entries: number;
}

export interface CatalogEntry {
  id: string;
  title: string;
  description: string;
  subsystem: string;
  risk_level: RiskLevel;
  fallback: boolean | null;
}

export interface IncidentRow {
  incident_id: string;
  source: string;
  type: string;
  trigger_event_id: string | null;
  trigger_ts: string;
  window_start: string;
  window_end: string;
  hit_count: number;
  keywords: string; // JSON-encoded list in the list endpoint
  demo: number;
  description: string;
  trigger_severity: Severity | null;
  status: IncidentStatus;
  pending_approvals: number;
  pending_escalations: number;
}

export interface IncidentDetail {
  incident_id: string;
  source: string;
  type: string;
  trigger_event_id: string | null;
  trigger_ts: string;
  window_start: string;
  window_end: string;
  hit_count: number;
  keywords: string[];
  demo: boolean;
  description: string;
  event_count: number;
  correlation_cached: boolean;
  rca_cached: boolean;
  actions_by_status: Record<string, number>;
}

export interface TimelineEntry {
  event_id: string;
  timestamp: string;
  role: TimelineRole;
  keyword: string;
  severity: Severity;
  summary: string;
  job_id: string | null;
  is_anchor: boolean;
}

export interface QaoaResult {
  status: string;
  reason?: string;
  n_qubits?: number;
  runtime_s?: number;
  compute_s?: number;
  energy?: number;
  [key: string]: unknown;
}

export interface TimelineResponse {
  cluster_size: number;
  timeline: {
    entries: TimelineEntry[];
    trigger_id: string | null;
    symptom_id: string | null;
    start: string | null;
    end: string | null;
    duration_s: number;
    n_events: number;
  };
  correlation: {
    n_events: number;
    n_clusters: number;
    louvain_runtime_s: number;
    ari: number | null;
    notes: string[];
    qaoa: QaoaResult;
  };
}

export interface CorrelationResponse {
  incident_id: string;
  n_events: number;
  classical: { method: string; n_clusters: number; runtime_s: number; largest_clusters: number[] };
  quantum: QaoaResult;
  ari: number | null;
  notes: string[];
}

export interface EarlyWarningAlert {
  subsystem: string;
  matched_incident_type: string;
  similarity_score: number;
  matched_event_ids: string[];
  window_start: string;
  window_end: string;
  matched_incident_id: string | null;
}

export interface Prediction extends EarlyWarningAlert {
  alert_id: string;
  status: "active" | "dismissed" | "opened";
  incident_id: string | null;
  nominal_lead_s: number;
}

export interface Hypothesis {
  cause: string;
  confidence: number;
  evidence_event_ids: string[];
  runbook_refs: string[];
}

export interface RcaResult {
  hypotheses: Hypothesis[];
  insufficient_evidence: boolean;
  reason?: string;
  transient?: boolean;
  llm_called?: boolean;
  dropped_references?: number;
  retrieved?: { chunk_id: string; score: number; source: string }[];
}

export interface ActionRow {
  incident_id: string;
  action_id: string;
  title: string;
  description: string;
  subsystem: string;
  risk_level: RiskLevel;
  status: ActionStatus;
  hypothesis_cause: string;
  confidence: number;
  evidence_event_ids: string[];
  runbook_refs: string[];
  created: string;
}

export interface MetricStat {
  mean: number;
  std: number;
}

export interface QuantumVsClassical {
  status: string;
  n_labeled: number;
  n_positive: number;
  n_negative: number;
  features: string[];
  cv: string;
  results: Record<string, { precision: MetricStat; recall: MetricStat; auc: MetricStat }>;
  note?: string;
}

export interface AuditEntry {
  id: number;
  timestamp: string;
  operator: string;
  incident_id: string | null;
  action_id: string | null;
  decision: string;
  evidence_shown: Record<string, unknown>;
  risk_level: RiskLevel | null;
}

export interface UploadResult {
  batch_id: string;
  filename: string;
  host: string;
  attach_to: string | null;
  size_bytes: number;
  records: number;
  first_ts: string;
  last_ts: string;
  events_in_attached_window: number | null;
  incidents_created: string[];
  audit_id: number;
  created: string;
}

export interface UploadRow {
  batch_id: string;
  created: string;
  operator: string;
  filename: string;
  host: string;
  attach_to: string | null;
  size_bytes: number;
  records: number;
  first_ts: string;
  last_ts: string;
  events_in_attached_window: number | null;
  incidents: string[];
}
