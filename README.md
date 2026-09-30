# Agentic Incident Commander — operator dashboard

React + TypeScript (Vite) dashboard for the Incident Commander engine: it shows incidents discovered in a Unisys
ClearPath MCP SUMLOG, their timeline, root cause and risk-classified actions, early warnings, and the append-only
audit log. All data comes from the FastAPI backend in [`../IncidentCommander`](../IncidentCommander).

## Run

```bash
# 1. backend (from IncidentCommander/)
uvicorn api.main:app --host 127.0.0.1 --port 8000

# 2. frontend (from this folder), Node 20+
npm install
cp .env.example .env        # VITE_API_BASE_URL=http://127.0.0.1:8000
npm run dev                 # http://localhost:5173
# or: npm run build && npm run preview   # http://localhost:4173
```

If the backend is not reachable the app shows a "Backend offline" banner.

## Pages

| Page | What it shows |
|---|---|
| Landing `/` | Alerts → incidents headline |
| Dashboard | Stats, incidents, early warnings, approval queue, recent activity, Run ingest |
| Incidents | All incident windows with severity, status and pending approvals |
| Incident detail | Timeline (trigger / propagation / symptom), Root cause, Actions, Quantum vs classical |
| Early warnings / Predictor | Pattern matches with similarity, dismiss or open as incident, model comparison |
| Upload SUMLOG | Upload LOGANALYZER exports for parsing and incident discovery |
| Audit log | Every decision with operator, risk tier and evidence |

## Rules the UI follows

- The LLM only suggests; risk tiers come from `action_catalog.yaml` in the backend.
- Only "needs approval" actions show Approve / Reject; "forbidden" actions can only be escalated; safe actions are auto-approved.
- Every decision is written to the append-only audit log.
- Root cause analysis for an incident without a cached result runs only when the operator asks (the LLM call can take minutes).
- Quantum results are reported as measured, without claims of advantage.

## Code map

- `src/api/index.ts` — API client (base URL from `VITE_API_BASE_URL`)
- `src/context/IncidentContext.tsx` — shared data and actions (approve, dismiss, upload, ingest…)
- `src/pages/` — pages and incident tabs · `src/components/` — sidebar, rows, badges, dialogs
- `docs/BACKEND_API.md` — endpoint contract · `docs/BACKEND_PROMPT.md` — prompt to build/verify the backend

Operator identity (`OP_SGURUPR`) is a placeholder until authentication exists.
