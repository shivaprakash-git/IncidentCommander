# Prompt: build / verify the FastAPI backend for the Incident Commander dashboard

Copy everything inside the box below into your AI coding agent (or hand it to a developer). It assumes the
agent can read both repositories. The contract it implements is [BACKEND_API.md](BACKEND_API.md).

---

```text
You are a senior Python/FastAPI engineer on the "Agentic Incident Commander" project (Unisys ClearPath MCP
operations). Your job is to make sure the FastAPI backend serves every endpoint the React dashboard needs,
exactly as specified in the contract file, without breaking anything that already exists.

<repositories>
- Backend (edit this): C:\ICF - backend\IncidentCommander-repo\IncidentCommander
  - api/main.py is a thin FastAPI layer; all logic lives in engine/*.py
  - action_catalog.yaml is the ONLY source of risk_level
  - tests/ uses pytest + fastapi.testclient on temporary SQLite databases
  - Python venv: C:\ICF - backend\venv-aic\Scripts\python.exe
- Running backend: http://127.0.0.1:8000  (uvicorn api.main:app --host 127.0.0.1 --port 8000; Swagger UI at /docs)
- Frontend (read only): C:\Incident commander frontend
  - Contract: docs/BACKEND_API.md  <-- the source of truth for paths, params, bodies and response fields
  - UI types: src/types/index.ts ; current mock data: src/mock/data.ts ; API stubs: src/api/index.ts
</repositories>

<non_negotiable_rules>
1. The LLM only suggests. risk_level (safe | needs_approval | forbidden) comes only from action_catalog.yaml.
   No code path may copy LLM output into a risk level.
2. safe actions are auto_approved and audited as "auto-approved" by "system"; they never enter the queue.
   needs_approval: pending -> approved | rejected | escalated. forbidden: escalate only (approve/reject -> 409).
3. Every decision writes exactly one audit entry: approve, reject, escalate, auto-approved, warning_dismissed,
   opened_as_incident, log_uploaded, ingest. Status change and audit row commit in one transaction.
4. audit_log is append-only. Keep the SQLite BEFORE UPDATE / BEFORE DELETE triggers. Never add edit/delete routes.
5. Early warnings are advisory until an operator opens one as an incident.
6. Report quantum results honestly. Never add fields or copy implying quantum advantage. Do not invent
   per-alert QSVM scores or time-to-impact forecasts that the engine does not compute.
</non_negotiable_rules>

<scope_lock>
- Do NOT remove, rename or change the meaning of any existing route, parameter, response field, table or
  function. Only add: new routes, new optional parameters, new response fields, new tables, new functions.
- Existing field types must stay the same (e.g. /incidents "keywords" stays a JSON string, "demo" stays 0/1).
- Do not change correlation, QAOA, RCA, precursor-matching or risk-classification logic.
- Do not add dependencies. (SUMLOG upload takes the raw request body, so python-multipart is not needed.)
- Keep routes thin: put new logic in engine/ modules, mirroring the existing style.
- Do not modify the real events.db, data/ or cache/ during development; tests must use temp paths.
- There may be uncommitted changes from other people in the repo. Leave them alone. Do not commit.
</scope_lock>

<step_0_gap_analysis>
Before editing anything:
1. Read api/main.py, engine/approval.py, engine/pipeline.py, engine/precursor.py, engine/db.py,
   engine/actions.py, engine/config.py, tests/test_api.py and the frontend's docs/BACKEND_API.md.
2. For each of the 23 endpoints in BACKEND_API.md section 1, report: exists as specified / exists but missing
   fields or params / missing. List the exact gaps.
3. STOP and show me the gap table before implementing.
</step_0_gap_analysis>

<implementation>
Implement only the gaps from step 0. The contract expects, in summary:

System
- GET /health adds: last_ingest_at, rule_engine_version (hash + size of action_catalog.yaml),
  llm_configured (chat key present), quantum_solver ("running" while a quantum=true call is in progress, else "idle").
- GET /catalog: [{id, title, description, subsystem, risk_level, fallback}] from action_catalog.yaml.
- POST /ingest additionally records the run (ingest_runs table) and appends an "ingest" audit entry by "system".

Incidents
- GET /incidents keeps all columns and adds trigger_severity, status (open | mitigating),
  pending_approvals (needs_approval+pending), pending_escalations (forbidden+pending).

Actions and audit
- approve/reject/escalate accept an optional "note" in the JSON body, stored in evidence_shown.note.
  Bodies without "note" must behave exactly as before.
- GET /audit entries add risk_level (from the action row; null for non-action entries).
- Add a public approval.log_event(conn, operator, decision, incident_id=None, action_id=None, evidence=None)
  for non-action audit entries, writing to the same append-only table.

Early warnings
- GET /predictions: each alert adds alert_id (deterministic: "PRED-" + sha1(type|window_start)[:8]),
  status (active | dismissed | opened), incident_id, nominal_lead_s (= precursor.LEAD_MIN * 60).
  Add optional include_decided=true; false hides dismissed/opened alerts.
- POST /predictions/{alert_id}/dismiss  body {operator, reason}: reason required (422), 404 if not in the
  current scan, 409 if already decided. Store in prediction_decisions; audit "warning_dismissed".
- POST /predictions/{alert_id}/open-incident  body {operator}: create incident INC-Pnn (source "prediction",
  type = matched type, window = alert window, trigger = last matched event). Audit "opened_as_incident".

SUMLOG upload
- POST /sumlog/upload?filename=&host=&operator=&attach_to=  with raw file bytes as the body.
  Validate extension (.log .txt .csv .sum), non-empty, size <= UPLOAD_MAX_BYTES (env, default 50 MB; 413).
  Save under UPLOAD_DIR (env, default data/uploads) - resolve the directory at call time, not as a default arg.
  Parse with engine.parser.parse_lines using a batch id prefix ("UPxxxxxx-L000123") so ids never collide with
  the main export. If attach_to is empty, run discovery on the file and save candidates as INC-<batch>-NN
  (source "upload"); if set, 404 on unknown incident and report events_in_attached_window.
  Record in an uploads table, record an ingest run, audit "log_uploaded".
- GET /sumlog/uploads?limit=20: newest first, without the stored file path.
</implementation>

<testing>
- Add tests/test_api_frontend.py (temp DB, synthetic ingest, seeded RCA, monkeypatched NIM keys and
  precursor.recent_predictions for deterministic alerts, temp UPLOAD_DIR). Cover every new route, every new
  field, each error code (400/404/409/413/422), backwards compatibility of decision bodies without "note",
  and "exactly one audit entry per decision".
- Use tests/fixtures/mini_sumlog.txt for upload tests (it contains a SECURITY VIOLATION, so discovery
  creates one incident).
- Run the FULL suite: ..\..\venv-aic\Scripts\python.exe -m pytest tests -q
  All pre-existing tests must still pass. Confirm no files were written into the real data/ folder.
</testing>

<documentation>
- Add the new routes to the API table in the backend README (append rows; do not delete existing rows).
- Add UPLOAD_DIR and UPLOAD_MAX_BYTES as commented examples in .env.example.
- If the backend's behaviour differs from docs/BACKEND_API.md, report the difference instead of silently
  changing either side.
</documentation>

<done_when>
- All 23 endpoints in BACKEND_API.md respond with the documented shapes (check with TestClient and /docs).
- Full pytest suite passes, including the new tests.
- Pending approvals (/actions?status=pending) and /audit never disagree for the same action.
- No existing route, field, table or function was removed or renamed.
</done_when>

<reporting>
When finished, output:
- Completed: bullet list of what was added or extended, per endpoint
- Files changed / added: paths
- Test result: counts before and after
- Assumptions and open questions (e.g. anything that needs the MCP problem owner to confirm)
Ask before: adding a dependency, changing an existing response field, touching risk/correlation/RCA logic,
or modifying the real database.
</reporting>
```

---

## Notes for whoever runs this prompt

- As of 30 Sept 2026 these endpoints are **already implemented** in the backend repo, with 75 passing tests.
  Running the prompt on that repo should end at step 0 with "no gaps", which makes it a useful verification pass.
- The prompt is also usable on a fresh copy of the original backend (before these additions) to rebuild them.
- Connecting the frontend to these endpoints is a separate task; see section 5 of
  [BACKEND_API.md](BACKEND_API.md) for the frontend changes it involves.
