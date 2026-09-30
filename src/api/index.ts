// Client for the FastAPI backend. Contract: docs/BACKEND_API.md
import type {
  ActionRow,
  AuditEntry,
  CatalogEntry,
  CorrelationResponse,
  Decision,
  EarlyWarningAlert,
  Health,
  IncidentDetail,
  IncidentRow,
  Prediction,
  QuantumVsClassical,
  RcaResult,
  Summary,
  TimelineResponse,
  UploadResult,
  UploadRow,
} from "../types";

export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, `Cannot reach the backend at ${API_BASE_URL}. Is it running?`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      // keep statusText
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

const qs = (params: Record<string, string | number | boolean | undefined | null>) => {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "");
  return entries.length ? `?${new URLSearchParams(entries.map(([k, v]) => [k, String(v)]))}` : "";
};

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  health: () => request<Health>("/health"),
  summary: () => request<Summary>("/summary"),
  catalog: () => request<CatalogEntry[]>("/catalog"),

  // Destructive: clears events, incidents and caches before re-parsing (actions and audit are kept).
  ingest: () => post<Record<string, unknown>>("/ingest?source=real"),

  incidents: () => request<IncidentRow[]>("/incidents"),
  incident: (id: string) => request<IncidentDetail>(`/incidents/${encodeURIComponent(id)}`),
  timeline: (id: string) => request<TimelineResponse>(`/incidents/${encodeURIComponent(id)}/timeline`),
  earlyWarning: (id: string) =>
    request<{ incident_id: string; alerts: EarlyWarningAlert[] }>(`/incidents/${encodeURIComponent(id)}/early-warning`),
  correlation: (id: string, quantum = false) =>
    request<CorrelationResponse>(`/incidents/${encodeURIComponent(id)}/correlation${qs({ quantum: quantum || undefined })}`),
  // Slow on first call (hosted LLM); cached afterwards.
  rca: (id: string, refresh = false) =>
    request<RcaResult>(`/incidents/${encodeURIComponent(id)}/rca${qs({ refresh: refresh || undefined })}`),
  incidentActions: (id: string) => request<ActionRow[]>(`/incidents/${encodeURIComponent(id)}/actions`),
  actions: (status?: string, riskLevel?: string) =>
    request<ActionRow[]>(`/actions${qs({ status, risk_level: riskLevel })}`),
  decide: (incidentId: string, actionId: string, decision: Decision, operator: string, note?: string) =>
    post<ActionRow>(
      `/incidents/${encodeURIComponent(incidentId)}/actions/${encodeURIComponent(actionId)}/${decision}`,
      { operator, ...(note ? { note } : {}) }
    ),

  predictions: () => request<{ alerts: Prediction[] }>("/predictions").then((r) => r.alerts),
  dismissPrediction: (alertId: string, operator: string, reason: string) =>
    post<Prediction>(`/predictions/${encodeURIComponent(alertId)}/dismiss`, { operator, reason }),
  openPrediction: (alertId: string, operator: string) =>
    post<Prediction>(`/predictions/${encodeURIComponent(alertId)}/open-incident`, { operator }),
  quantumVsClassical: () => request<QuantumVsClassical>("/predictions/quantum-vs-classical"),

  audit: (limit = 500) => request<AuditEntry[]>(`/audit${qs({ limit })}`),

  uploads: (limit = 20) => request<UploadRow[]>(`/sumlog/uploads${qs({ limit })}`),
};

// Raw-body upload with progress (fetch cannot report upload progress).
export function uploadSumlog(
  file: File,
  opts: { host: string; operator: string; attachTo?: string },
  onProgress: (pct: number) => void
): Promise<UploadResult> {
  const url = `${API_BASE_URL}/sumlog/upload${qs({
    filename: file.name,
    host: opts.host,
    operator: opts.operator,
    attach_to: opts.attachTo,
  })}`;
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        // non-JSON error body
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as UploadResult);
      else {
        const detail = (body as { detail?: unknown } | null)?.detail;
        reject(new ApiError(xhr.status, typeof detail === "string" ? detail : xhr.statusText || "Upload failed"));
      }
    };
    xhr.onerror = () => reject(new ApiError(0, `Cannot reach the backend at ${API_BASE_URL}.`));
    xhr.send(file);
  });
}
