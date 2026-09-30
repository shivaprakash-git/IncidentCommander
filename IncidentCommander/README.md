# Agentic Incident Commander — core engine (v1)

Ingests a real Unisys ClearPath MCP **SUMLOG** (LOGANALYZER text export), discovers real incident windows, correlates
events (Louvain vs QAOA), matches pre-incident patterns, diagnoses root cause with RAG + an LLM, and recommends
**risk-classified** actions for human approval with an append-only audit trail. Business logic lives in `engine/`;
`api/main.py` is a thin FastAPI wrapper. Every module runs standalone.

> **Numbers below come from an actual run** on `data/sumlog_export.txt` (LOGANALYZER SSR 64.0, SUMLOG #004853,
> 08/10/2023 11:02:32 → 08/14/2023 14:28:48). Nothing is projected or rounded up.

## Layout

```
engine/   config patterns models db | parser discovery generator | correlation | timeline precursor
          | nim rag rca | actions approval | qsvm | pipeline (orchestration used by CLI + API)
api/main.py            thin routes -> engine
action_catalog.yaml    ONLY source of risk_level (safe | needs_approval | forbidden)
runbooks/ incidents/   RAG corpus (7 runbooks, 3 past-incident write-ups)
tests/                 56 tests (pytest) + fixtures/mini_sumlog.txt
```

## Setup

```bash
python -m venv <somewhere>/aic          # see note 1
<venv>/python -m pip install -r requirements.txt
cp .env.example .env                    # then fill the two NVIDIA keys (git-ignored)
# put the export at data/sumlog_export.txt   (git-ignored)
<venv>/python -m pytest tests -q
```

Tested on Python 3.13 (the spec said 3.11; PennyLane 0.45.1 and everything else installed and passed on 3.13).

## Run each module standalone

| Module | Command |
|---|---|
| Parser (+slicing) | `python -m engine.parser --max-records 500 --show 10` · also `--start-line/--end-line`, `--start-time/--end-time` (`YYYY-MM-DD HH:MM:SS`), `--count-all`, `--no-db`. Default = first 5,000 records. |
| Discovery | `python -m engine.discovery [--save]` (scans the whole file) |
| Synthetic generator | `python -m engine.generator [--save] [--dump out.txt]` |
| Ingest (parse slice + discovery + incident windows + labelled set) | `python -m engine.pipeline ingest [--source real\|synthetic] [slice flags]` |
| Correlation | `python -m engine.correlation --test [--incident INC-R01] [--qubits 14] [--timeout 90]` |
| Timeline | `python -m engine.timeline --incident INC-R01` |
| Precursor | `python -m engine.precursor --build --real-negatives --selftest` · `--scan` |
| RAG | `python -m engine.rag "query" -k 3` · `--chunks` |
| RCA | `python -m engine.rca --incident INC-R01` (LLM call; can take minutes, see note 5) |
| Actions / approval demo | `python -m engine.approval --demo` |
| QSVM | `python -m engine.qsvm` (writes `cache/qsvm_result.json`) |

### End to end

```bash
python -m engine.pipeline ingest                 # ~20 s: slice + discovery + incident windows + labelled set
uvicorn api.main:app --port 8000
curl -X POST localhost:8000/discover             # full-file scan, no side effects on events
curl -X POST "localhost:8000/ingest?source=real&max_records=5000"     # NOTE: resets events/incidents/caches
curl localhost:8000/incidents?demo_only=true
```

`POST /ingest` clears `events`, `incidents`, `correlation_runs` and `rca_results` first (RCA results cost minutes
of LLM time; `actions`/`audit_log` are never cleared).

## API

| Route | Returns |
|---|---|
| `POST /ingest?source=real\|synthetic&start_line&end_line&start_time&end_time&max_records` | Ingest summary: slice size, discovery counts, window events pulled in, demo incidents (real vs synthetic), labelled-set size |
| `POST /discover` | Full-file scan: records scanned, hit records, keyword counts, candidate windows |
| `GET /incidents[?demo_only=true]` | Incidents: id, source (`real`/`synthetic`), type, trigger, window, hit count, `demo` flag |
| `GET /incidents/{id}/timeline[?quantum=true]` | Trigger-cluster timeline (trigger / propagation / symptom roles) + correlation summary (Louvain clusters + runtime, QAOA status/runtime, ARI). Cached; `quantum=true` runs QAOA if it has not run yet |
| `GET /incidents/{id}/early-warning` | Precursor alerts that would have fired in the 30 min before the trigger, matched against the library **excluding the incident itself** |
| `GET /predictions[?minutes=60&threshold=0.75]` | Alerts from a sliding-window scan of the most recent events |
| `GET /incidents/{id}/rca[?refresh=true]` | `{hypotheses:[{cause, confidence, evidence_event_ids, runbook_refs}], insufficient_evidence, retrieved, llm_called, ...}`; cached |
| `GET /incidents/{id}/actions` | Recommended actions with `risk_level` (from the YAML) and `status` |
| `POST /incidents/{id}/actions/{action_id}/approve\|reject\|escalate` body `{"operator":"..."}` | Updated action. `409` for illegal transitions, `404` for unknown ids |
| `GET /audit[?incident_id=&limit=]` | Append-only audit entries (newest first) |
| `GET /predictions/quantum-vs-classical` | QSVM vs classical result. **Registered only because Phase 5.5 produced a real result**; absent otherwise (no stub) |

Governance (from `action_catalog.yaml`, never the LLM): `safe` = informational, stored `auto_approved` and audited as
`auto-approved` by `system`, never enters the queue; `needs_approval` = `pending → approved|rejected|escalated`
(terminal in v1); `forbidden` = escalate-only (approve/reject → 409). `audit_log` is append-only enforced by SQLite
`BEFORE UPDATE/DELETE` triggers (verified: `DELETE` is refused).

## Results from the real run

### Parser / discovery
* **Whole-file parse: 34,720 records**, in **three** header shapes: 3-space `HH:MM:SS` (23,542, incl. 1,494 with no
  keyword → type `INFO`), unindented `HH:MM:SS.ffff` TIME/DIAG (10,968), and unindented `MM/DD/YYYY HH:MM:SS.ffff`
  BNAV/TCPIP (210). Dates come from the day lines. Non-record blocks (the "GENERAL MCP INFORMATION / HALT/LOAD UNIT"
  section, separators) are never glued onto the previous record.
* **Count gap:** LOGANALYZER states 72,230 records; the parser finds 34,720. Every timestamp-led line is counted (checked:
  no other header pattern with a digit-led line outside the three shapes), so the gap is **not explained by a missed
  header pattern**. Most likely LOGANALYZER counts SUMLOG entries that its text report does not print as separate
  records — *unverified*; flagged for follow-up.
* Default 5,000-record slice: 13.4 % `UNMAPPED`. Full file: 42.7 % `UNMAPPED` (`DIAG` 7,981, `INT` 4,481, `LIB` 1,794,
  `->` 205, `COD`, `DISK`, `DEIMP`, `DCKEY`, …). Mapped: BOT/EOT/OPEN/CLOSE/BOJ/EOJ (major 1), LOGON/LGOFF (major 4),
  EI (JOB/TASK_INFO), TIME (SYSTEM/TIME_MSG); BOJ/EOJ/LOGON/LGOFF come from the reference doc's Log Entry Classes table.
* **Discovery** (whole file, ~5 s): 46 hit records after the noise filter (`NO SUMLOG ENTRIES WERE DISCARDED`,
  `RECOVERY = DISCARD`, `HALT/LOAD UNIT/TIME` boot text are excluded; e.g. the 3 raw `HALT` hits and most of the 71
  `DISCARD` hits were boilerplate). Keywords: FAILED 36, SECURITY VIOLATION 10, VIOLATION 10, INVALID 4; no HALT,
  UNAUTHORIZED, ABEND, DISCARD hits survived. → **10 candidate windows** (5 `auth_failure_security_violation`, 5
  `linkage_failure`), ±15 min, overlaps merged (cap 60 min).
* **Demo incidents: 3 real, 0 synthetic** — `INC-R01` (08/10 11:26, repeated invalid usercode via NXEDIT with
  `Linklibrary to GSSAPI failed`), `INC-R06` (08/14 10:31, `LINKAGE FAILED DUE TO MISSING CODE FILE`), `INC-R09`
  (08/14 13:13, invalid usercode/password). The synthetic generator (3 planted scenarios, ~78 events) exists and is
  tested but was **not needed** for the demo path.

### Correlation benchmark (Louvain vs QAOA)
Graph: shared job/task/session + time proximity (10 min). QAOA is a **2-way min-cut QUBO on a 14-node subsample**
(stratified by Louvain community); ARI compares it with Louvain on the *same* subsample. Louvain on the full window is
canonical downstream.

| Incident | Events | Louvain clusters | Louvain time | Trigger cluster | QAOA (14 q) compute / wall* | ARI |
|---|---|---|---|---|---|---|
| INC-R01 | 1,925 | 30 | 1,053 ms | 93 | 37.1 s / 47.5 s | 0.343 |
| INC-R06 | 1,613 | 24 | 225 ms | 50 | 7.0 s / 10.7 s | 0.663 |
| INC-R09 | 3,932 | 43 | 574 ms | 87 | 8.3 s / 12.4 s | 0.729 |

\*wall includes spawning the killable child process and importing PennyLane. QAOA never blocks: it runs in a child
process with a timeout and any failure is recorded while Louvain continues.

### Precursor matcher (similarity-based, **not** a trained classifier)
Vector of 14 counts over the LEAD (10 min) window before each trigger. **Measured on real data:** with the always-present
traffic features (`diag/lib/logon`) included in the cosine, *every* normal window scored ≥ 0.75 (30/30 false alarms).
They are still stored in the vectors (QSVM uses them) but have weight 0 for matching. Result at threshold 0.75:
0/30 sampled normal windows alert (max 0.598); leave-one-out, 5 of 10 incidents are matched by another incident
(R01↔R05 auth; R07/R08/R10 linkage); the other 5 (R02, R03, R04, R06, R09) have **no anomaly signal** before their
trigger, so nothing can match them. `INC-R01` raises a genuine early warning (window 11:16:32→11:26:03, matches R05 at
0.907) driven by the GSSAPI failure one second before the security violation.

### RCA (NVIDIA NIM, forced JSON, temp 0.2)
* `INC-R01`: hypothesis "Kerberos/GSSAPI misconfiguration causing fallback to usercode/password authentication which
  then fails", confidence 0.9, evidence `L014310, L014393, L014398` — all real events; 0 references dropped as hallucinated.
* `INC-R06`: best retrieval similarity 0.394 < 0.4, so the **guard returned `insufficient_evidence` without calling the
  LLM** (designed behaviour; it is a near miss, so the threshold is a tunable trade-off).
* `INC-R09`: retrieval succeeded (top hit `past_auth_failure_burst#0`, 0.521) but the hosted model returned **HTTP 504
  twice**, so no hypothesis was produced. The outage is marked `transient` and not cached; re-run `GET /incidents/INC-R09/rca`
  when NIM is responsive. The pipeline degrades to `insufficient_evidence` plus the fallback safe action, and does not crash.

### QSVM (Phase 5.5 — built, with numbers)
N = **40** labelled windows (10 pre-incident from real incidents, 30 sampled normal); top-5 variance features
(`lib_events, diag_events, logon_events, warn_events, linkage_failed`) scaled to [0, π]; AngleEmbedding, 1 layer,
`default.qubit` overlap kernel → `SVC(precomputed)`; classical SVM (RBF) and GBM on identical features and folds;
10× repeated stratified 5-fold, pooled out-of-fold predictions, no tuning.

| Model | Precision | Recall | AUC |
|---|---|---|---|
| QSVM | 0.638 ± 0.036 | 0.760 ± 0.080 | 0.886 ± 0.011 |
| SVM (RBF) | 0.653 ± 0.020 | 0.900 ± 0.000 | **0.917 ± 0.015** |
| GBM | **0.794 ± 0.059** | 0.710 ± 0.094 | 0.852 ± 0.060 |

Classical is as good or better; there is no quantum advantage here. Caveats: 10 positives is tiny; one AngleEmbedding
layer yields a product-state (classically simulable) kernel; and the top-variance features are mostly traffic-volume
counts, so all three models may be separating *busy* windows from *quiet* ones rather than detecting true precursors.
The similarity matcher above remains the v1 prediction mechanism.

## v1 / v2 scope boundary
**v1 (this build):** everything above. **v2 (not built):** QUBO feature selection ahead of QSVM — gated on far more real
labelled data at volume (10 real positives cannot support it), plus a UI, real auth, reranker, and a vector-DB server.

## Notes and deviations
1. **Windows Store Python** virtualises writes under `AppData\Roaming`, so the venv must live outside it and the project
   in an ordinary folder.
2. Embedding model: the catalog has no exact `nemotron-3-embed-1b`; the client resolved the closest match,
   `nvidia/llama-nemotron-embed-vl-1b-v2` (chat: `google/gemma-4-31b-it`). Ids are cached in `cache/nim_models.json`;
   embeddings are cached on disk by hash so runs never re-embed unchanged chunks.
3. The NIM client keeps TLS verification on and trusts certifi plus the Windows root store (corporate proxy).
4. Incident **trigger** = earliest hit of the window's most severe keyword class. Timeline roles follow the spec
   (first event of the cluster = "trigger"), and the discovery hit is flagged as the anchor (`*`).
5. **LLM latency:** the hosted model is slow — a one-line prompt took 211 s and the `INC-R01` RCA about 10 min. Chat calls
   use a 420 s timeout with one retry. Outages and unparseable replies are marked `transient` and **not cached**; low
   retrieval similarity is a real verdict and is cached.
6. Synthetic scenarios include low-grade warnings *before* the trigger so the matcher has something to match.
7. **Rotate the two NVIDIA API keys** — they were pasted into a chat to create `.env`.

## Deliverables checklist
- [x] Phase 1: `engine/parser.py`, `discovery.py`, `generator.py`, `events.db`, console summary
- [x] Phase 2: `engine/correlation.py` (`correlate()`, `--test`)
- [x] Phase 3: `engine/timeline.py`, `precursor.py`, persisted labelled vectors
- [x] Phase 4: `runbooks/` (7), `incidents/` (3), `engine/rag.py`, `engine/rca.py` (`INC-R01` verified live; R06 guard; R09 blocked by NIM 504)
- [x] Phase 5: `action_catalog.yaml`, `engine/actions.py`, `engine/approval.py`, full approve→audit cycle
- [x] Phase 5.5: `engine/qsvm.py`, result in the QSVM section above
- [x] Phase 6: `api/main.py`, all routes exercised with curl (see API table)
- [x] Phase 7: this README, `.env.example` (blank keys), `.env` git-ignored
