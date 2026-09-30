# Backend API for the Incident Commander dashboard

Every FastAPI endpoint this React frontend needs, what it sends, and what it gets back.

- **Backend:** `C:\ICF - backend\IncidentCommander-repo\IncidentCommander` (FastAPI, `api/main.py`)
- **Base URL:** `http://127.0.0.1:8000` (no `/api` prefix)
- **Run:** `..\..\venv-aic\Scripts\python.exe -m uvicorn api.main:app --port 8000` · Swagger UI at `/docs`
- **Detailed reference with real sample responses:** `docs/frontend-api/` in the backend repo

Status column: **Exists** = already in the backend · **Extended** = exists, with extra fields or optional
parameters added for this UI · **New** = added for this UI.

---

## 1. Endpoint list

| # | Method | Path | Status | Used by (page) |
|---|---|---|---|---|
| 1 | GET | `/health` | Extended | Sidebar health block |
| 2 | GET | `/summary` | Exists | Landing, Dashboard headline, Timeline "N of M" |
| 3 | GET | `/catalog` | New | Action names and risk tiers everywhere |
| 4 | POST | `/ingest` | Extended | Dashboard "Run ingest" |
| 5 | POST | `/discover` | Exists | (admin / optional) |
| 6 | POST | `/sumlog/upload` | New | Upload SUMLOG |
| 7 | GET | `/sumlog/uploads` | New | Upload SUMLOG "Recent uploads" |
| 8 | GET | `/incidents` | Extended | Incidents, Dashboard, Upload "attach to" list |
| 9 | GET | `/incidents/{id}` | Exists | Incident header |
| 10 | GET | `/incidents/{id}/timeline` | Exists | Timeline tab |
| 11 | GET | `/incidents/{id}/early-warning` | Exists | Timeline tab precursor section, lead-time card |
| 12 | GET | `/incidents/{id}/correlation` | Exists | Quantum vs classical tab |
| 13 | GET | `/incidents/{id}/rca` | Exists | Root cause tab |
| 14 | GET | `/incidents/{id}/actions` | Exists | Actions tab |
| 15 | GET | `/actions` | Exists | Dashboard "Awaiting your approval", sidebar count |
| 16 | POST | `/incidents/{id}/actions/{action_id}/approve` | Extended | Approval dialog |
| 17 | POST | `/incidents/{id}/actions/{action_id}/reject` | Extended | Actions tab |
| 18 | POST | `/incidents/{id}/actions/{action_id}/escalate` | Extended | Escalate dialog |
| 19 | GET | `/predictions` | Extended | Early warnings, Dashboard banner, sidebar count |
| 20 | POST | `/predictions/{alert_id}/dismiss` | New | Dismiss dialog |
| 21 | POST | `/predictions/{alert_id}/open-incident` | New | "Open as incident" |
| 22 | GET | `/predictions/quantum-vs-classical` | Exists (conditional) | Predictor panel model comparison |
| 23 | GET | `/audit` | Extended | Audit log, Dashboard "Recent activity" |

---

## 2. Conventions

| Topic | Rule |
|---|---|
| Format | JSON in and out. Exception: `POST /sumlog/upload` takes raw file bytes as the body |
| Operator | Placeholder identity, not auth. Send `operator` in the JSON body (decisions, warnings) or query (upload). Use the sidebar ID, e.g. `OP_SGURUPR` |
| Time | ISO 8601 without time zone. Event times are **MCP local time** from the SUMLOG |
| Errors | `{"detail": "..."}` · `400` bad input · `404` unknown id · `409` illegal state change · `413` too large · `422` validation |
| Slow calls | `/rca` (and `/actions`, which needs RCA) can take minutes on first call, then cached. `?quantum=true` runs QAOA (up to ~1 min) |
| CORS | `CORS_ORIGINS` in backend `.env`, e.g. `http://localhost:5173,http://127.0.0.1:4173` |

---

## 3. Endpoints by page

### Sidebar and system

**1. `GET /health`**

```json
{
  "status": "ok", "events": 14906, "incidents": 10, "data_file_present": true,
  "nim_chat_key_set": true, "nim_embed_key_set": true, "qsvm_result": true,
  "last_ingest_at": "2026-09-30T15:51:10",
  "rule_engine_version": "catalog-2952420e (19 actions)",
  "llm_configured": true,
  "quantum_solver": "idle"
}
```

Sidebar rows: Ingest ← `last_ingest_at` · Rule engine ← `rule_engine_version` · LLM ← `llm_configured`
(key present, not a reachability test) · Quantum solver ← `quantum_solver` (`idle` | `running`).

**2. `GET /summary`**

```json
{ "events_total": 78, "alerts": 25, "incidents": 3, "headline": "25 alerts -> 3 incidents (3 demo)",
  "events_by_severity": {"CRIT": 9, "WARN": 16, "INFO": 53}, "pending_approvals": 3, "audit_entries": 5 }
```

"Alerts grouped X → Y" = `alerts` → `incidents`. Timeline "N of M" uses `events_total`.

**3. `GET /catalog`**

```json
[{ "id": "add_disk_to_family", "title": "Add a disk to the family (RC)", "description": "...",
   "subsystem": "storage", "risk_level": "needs_approval", "fallback": null }]
```

Single source of action names and risk tiers (`safe` | `needs_approval` | `forbidden`), read from
`action_catalog.yaml`. No LLM output can set a risk tier.

### Dashboard

**4. `POST /ingest?source=real|synthetic[&start_line&end_line&start_time&end_time&max_records]`**

> Destructive: clears events, incidents, correlation and RCA caches before re-parsing (actions and audit are
> kept). The UI must ask for confirmation. Writes an `ingest` audit entry and updates `last_ingest_at`.

Returns an ingest summary (`events_total`, `demo_incidents`, `discovery`, ...). `400` if the export is missing.

**15. `GET /actions?status=pending&risk_level=needs_approval`** → "Awaiting your approval".
Same row shape as endpoint 14. `status` ∈ `pending|auto_approved|approved|rejected|escalated`.

Also on the dashboard: `GET /incidents`, `GET /predictions?include_decided=false`, `GET /audit?limit=4`.

### Incidents

**8. `GET /incidents[?demo_only=true]`**

```json
[{
  "incident_id": "INC-R01", "source": "real", "type": "auth_failure_security_violation",
  "trigger_event_id": "L014393", "trigger_ts": "2023-08-10T11:26:04",
  "window_start": "2023-08-10T11:11:04", "window_end": "2023-08-10T11:41:04",
  "hit_count": 4, "keywords": "[\"SECURITY VIOLATION\"]", "demo": 1,
  "description": "4 keyword hit(s); first: ...",
  "trigger_severity": "CRIT", "status": "open", "pending_approvals": 1, "pending_escalations": 0
}]
```

`status` = `mitigating` once a non-safe action is approved, else `open`. Pending counts fill in after the
incident's actions have been fetched once.

### Incident detail

**9. `GET /incidents/{id}`** → header: incident row + `event_count`, `rca_cached`, `correlation_cached`,
`actions_by_status`. Cheap; no LLM work.

**10. `GET /incidents/{id}/timeline[?quantum=false]`**

```json
{
  "cluster_size": 6,
  "timeline": {
    "entries": [{ "event_id": "L014393", "timestamp": "2023-08-10T11:26:04", "role": "trigger",
                  "keyword": "INFO", "severity": "CRIT", "summary": "SECURITY VIOLATION - ...",
                  "job_id": "6619", "is_anchor": true }],
    "trigger_id": "L014393", "symptom_id": "L014398", "start": "...", "end": "...", "duration_s": 160.0, "n_events": 6
  },
  "correlation": { "n_events": 25, "n_clusters": 6, "louvain_runtime_s": 0.004, "ari": null,
                   "qaoa": { "status": "skipped" } }
}
```

Phase sections ← `entries[].role` (`trigger` | `propagation` | `symptom`, assigned by the timeline builder, not
the LLM). Entities ← distinct `job_id`.

**11. `GET /incidents/{id}/early-warning`**

```json
{ "incident_id": "INC-R01", "alerts": [{ "subsystem": "security/logon",
  "matched_incident_type": "auth_failure_security_violation", "similarity_score": 0.907,
  "matched_event_ids": ["L014310"], "window_start": "...", "window_end": "...", "matched_incident_id": "INC-R05" }] }
```

Precursor section ← `alerts[0]`; lead = `trigger_ts − window_end`. Empty list → "None".

**12. `GET /incidents/{id}/correlation[?quantum=false]`**

```json
{ "n_events": 25, "classical": { "method": "louvain", "n_clusters": 6, "runtime_s": 0.004 },
  "quantum": { "status": "skipped" }, "ari": null, "notes": [] }
```

Run QAOA with `?quantum=true` behind a button. There is no accuracy figure; show "Agreement (ARI)".

**13. `GET /incidents/{id}/rca[?refresh=false]`**

```json
{ "hypotheses": [{ "cause": "...", "confidence": 0.9, "evidence_event_ids": ["L014310"],
                   "runbook_refs": ["auth_failure_security_violation#0"] }],
  "insufficient_evidence": false, "llm_called": true }
```

`insufficient_evidence: true` → show that card, not a guess. `transient: true` → LLM outage, offer retry.

**14. `GET /incidents/{id}/actions`**

```json
[{ "incident_id": "INC-S01", "action_id": "add_disk_to_family", "title": "Add a disk to the family (RC)",
   "risk_level": "needs_approval", "status": "pending", "hypothesis_cause": "...", "confidence": 0.8,
   "evidence_event_ids": ["S1-L000012"], "runbook_refs": ["sumlog_full#0"], "created": "..." }]
```

| `risk_level` | Starts as | Allowed | UI |
|---|---|---|---|
| `safe` | `auto_approved` (audited `auto-approved` by `system`) | none | "Auto · Safe", no button |
| `needs_approval` | `pending` | approve, reject | Approve dialog + Reject |
| `forbidden` | `pending` | escalate only | Escalate |

**16–18. `POST /incidents/{id}/actions/{action_id}/approve | reject | escalate`**

```json
{ "operator": "OP_SGURUPR", "note": "optional, stored in the audit entry" }
```

Returns the updated action row. `404` unknown · `409` already decided / forbidden approve / any decision on safe.
The audit entry stores the backend's own evidence for the action (hypothesis, event ids, runbooks) plus the note.

### Early warnings

**19. `GET /predictions[?minutes=60&threshold=0.75&include_decided=true]`**

```json
{ "alerts": [{ "alert_id": "PRED-6173353E", "status": "active", "incident_id": null,
  "subsystem": "security/logon", "matched_incident_type": "auth_failure_security_violation",
  "similarity_score": 0.91, "matched_event_ids": ["L014310"], "matched_incident_id": "INC-R05",
  "window_start": "...", "window_end": "...", "nominal_lead_s": 600 }] }
```

- Use `include_decided=false` for the list and counts.
- Show `similarity_score`. There are **no per-alert Classical / Q-SVM scores**.
- `nominal_lead_s` is the matcher's look-back window, **not** a time-to-impact forecast. No countdown.

**20. `POST /predictions/{alert_id}/dismiss`** body `{ "operator": "OP_SGURUPR", "reason": "required" }`
→ alert with `status: "dismissed"`; audit `warning_dismissed`. `404` unknown/changed · `409` decided · `422` no reason.

**21. `POST /predictions/{alert_id}/open-incident`** body `{ "operator": "OP_SGURUPR" }`
→ alert with `status: "opened"`, `incident_id: "INC-P01"`; audit `opened_as_incident`. Navigate to the new incident.

**22. `GET /predictions/quantum-vs-classical`** → aggregate QSVM vs SVM vs GBM (precision, recall, AUC).
Only registered when a QSVM result exists; hide the section on `404`.

### Upload SUMLOG

**6. `POST /sumlog/upload?filename=...&host=...&operator=...[&attach_to=INC-R01]`** — raw bytes body

```ts
fetch(`${API}/sumlog/upload?${new URLSearchParams({ filename: file.name, host, operator })}`,
      { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file });
```

```json
{ "batch_id": "UPCEE5E7", "filename": "SUMLOG-MCP-PROD1.log", "host": "MCP-PROD1", "attach_to": null,
  "size_bytes": 1330, "records": 8, "first_ts": "2023-08-10T23:58:59", "last_ts": "2023-08-11T00:00:10",
  "events_in_attached_window": null, "incidents_created": ["INC-UPCEE5E7-01"], "audit_id": 5, "created": "..." }
```

Accepts `.log .txt .csv .sum`, up to 50 MB. `400` bad type / empty / no records · `404` unknown `attach_to` · `413` too large.
Event ids are batch-prefixed, so uploads never overwrite the main export. Audit: `log_uploaded`.

**7. `GET /sumlog/uploads?limit=20`** → recent uploads, newest first (same fields, `incidents` list).

### Audit log

**23. `GET /audit[?incident_id&operator&decision&since&until&limit=200]`**

```json
[{ "id": 3, "timestamp": "2026-09-30T15:51:11", "operator": "OP_SGURUPR", "incident_id": "INC-S01",
   "action_id": "add_disk_to_family", "decision": "approved", "risk_level": "needs_approval",
   "evidence_shown": { "hypothesis": "...", "confidence": 0.8, "evidence_event_ids": ["S1-L000012"],
                       "runbook_refs": ["sumlog_full#0"], "note": "Verified family space" } }]
```

Newest first. Seq ← `id`. Time-range filter → `since = now − range`. Append-only (DB triggers refuse update/delete).

| `decision` | Badge |
|---|---|
| `auto-approved` | Auto · Safe |
| `approved` / `rejected` / `escalated` | Approved / Rejected / Escalated |
| `warning_dismissed` | Warning dismissed |
| `opened_as_incident` | Opened as incident |
| `log_uploaded` | Log uploaded |
| `ingest` | System |

---

## 4. Frontend mock → backend field map

| Frontend (`src/mock/data.ts`) | Backend |
|---|---|
| `Incident.id` / `title` | `incident_id` / `description` (or humanised `type`) |
| `Incident.severity` | `trigger_severity`: `CRIT`→critical, `WARN`→warning, `INFO`→info |
| `startTime` / `endTime` | `window_start` / `window_end` |
| `RawEvent.phase` / `message` | timeline `role` / `summary` |
| `Incident.precursor` | `/early-warning` `alerts[0]` |
| action `catalogId`, `name`, `ruleId` | `action_id`, `title`, `action_catalog.yaml#<action_id>` |
| action status `executed` | `auto_approved` |
| audit `seq`, decision `auto_safe`, `system` | `id`, `auto-approved`, `ingest` |
| warning `id`, `leadTimeSeconds` | `alert_id`, `nominal_lead_s` (look-back, not forecast) |
| warning `classicalScore` / `quantumScore` | not available; use `similarity_score` |

## 5. Frontend changes required when wiring up

> **Status (30 Sept 2026): done.** The frontend now reads everything from this API; `src/mock/data.ts` has been
> removed. Client: `src/api/index.ts` · shared data: `src/context/IncidentContext.tsx`. Root cause and actions for
> incidents without a cached RCA wait for an explicit "Run root cause analysis" click, because the LLM call is slow.
> `GET /predictions` takes ~10 s on the real data, so it loads separately and is not re-run on every refresh.

1. Replace `src/mock/data.ts` reads and `src/api/index.ts` stubs with calls to the endpoints above.
2. Remove the "Run" button on safe actions (backend auto-approves them).
3. Early warnings: show "Similarity 0.91"; drop the ETA countdown.
4. Quantum tab: "Agreement (ARI)" instead of "Accuracy".
5. Time label: "MCP local time" instead of "UTC".
6. "Run ingest": add a confirmation step (destructive).
7. Upload: send the raw file body (no multipart).
8. After any decision, refetch `/incidents`, `/actions?status=pending&risk_level=needs_approval` and `/audit`.
