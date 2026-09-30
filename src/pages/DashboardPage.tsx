import React, { useState } from "react";
import { Link } from "react-router-dom";
import { useIncidents } from "../context/IncidentContext";
import { IncidentRow, PredictionRow, predictionTitle } from "../components/Rows";
import { RiskBadge } from "../components/RiskBadge";
import { DecisionBadge } from "../components/DecisionBadge";
import { ConfirmModal } from "../components/modals/ConfirmModal";
import { Loading, ErrorState } from "../components/States";
import { TIMEZONE_LABEL, formatDateTime } from "../lib/format";
import { describeAudit } from "../lib/audit";

export const DashboardPage: React.FC = () => {
  const {
    summary,
    incidents,
    activePredictions,
    pendingApprovals,
    audit,
    health,
    catalog,
    loading,
    error,
    ingesting,
    runIngest,
    refresh,
    predictionsLoading,
  } = useIncidents();
  const [bannerDismissed, setBannerDismissed] = useState(false);
  const [confirmIngest, setConfirmIngest] = useState(false);

  if (loading) return <div className="page"><Loading label="Loading live data from the backend…" /></div>;
  if (error && !summary) return <div className="page"><ErrorState error={error} onRetry={() => void refresh()} /></div>;

  const criticalCount = incidents.filter((i) => i.trigger_severity === "CRIT").length;
  const firstWarning = activePredictions[0];
  const openIncidents = [...incidents]
    .sort((a, b) => Number(b.status === "open") - Number(a.status === "open") || b.trigger_ts.localeCompare(a.trigger_ts))
    .slice(0, 5);

  return (
    <div className="page">
      <div className="page-header">
        <h4>Dashboard</h4>
        <p className="text-2 mb-0">Live data from the SUMLOG export. Event times are {TIMEZONE_LABEL}.</p>
      </div>

      {firstWarning && !bannerDismissed && (
        <div className="banner-predict" role="status">
          <i className="bi bi-graph-up-arrow text-predict fs-5 flex-shrink-0"></i>
          <div className="flex-grow-1 min-w-0" style={{ fontSize: "0.9rem" }}>
            <strong>
              {activePredictions.length} early warning{activePredictions.length > 1 ? "s" : ""}
            </strong>{" "}
            — {predictionTitle(firstWarning)} matched · similarity {firstWarning.similarity_score.toFixed(2)}
          </div>
          <Link to={`/predictor/${firstWarning.alert_id}`} className="btn btn-sm btn-outline-primary flex-shrink-0">
            Review
          </Link>
          <button type="button" className="btn-close flex-shrink-0" aria-label="Dismiss banner" onClick={() => setBannerDismissed(true)}></button>
        </div>
      )}

      <div className="row g-3 mb-4">
        <div className="col-12 col-md-6 col-xl-3">
          <div className="panel panel-pad h-100">
            <div className="d-flex align-items-start justify-content-between gap-2">
              <div className="small-label">Alerts grouped</div>
              <button
                type="button"
                className="btn btn-sm btn-outline-primary py-0 px-2"
                onClick={() => setConfirmIngest(true)}
                disabled={ingesting}
              >
                {ingesting ? (
                  <>
                    <span className="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>Ingesting
                  </>
                ) : (
                  "Run ingest"
                )}
              </button>
            </div>
            <div className="stat-value" style={{ color: "var(--uc-teal)" }}>
              {summary?.alerts ?? "—"} → {summary?.incidents ?? "—"}
            </div>
            <div className="small-label mt-1">
              {summary?.events_total.toLocaleString()} events · last ingest {health?.last_ingest_at ? formatDateTime(health.last_ingest_at) : "not recorded"}
            </div>
          </div>
        </div>
        <div className="col-6 col-md-6 col-xl-3">
          <div className="panel panel-pad h-100">
            <div className="small-label">Critical incidents</div>
            <div className="stat-value" style={{ color: "var(--uc-critical)" }}>{criticalCount}</div>
            <div className="small-label mt-1">of {incidents.length} incidents</div>
          </div>
        </div>
        <div className="col-6 col-md-6 col-xl-3">
          <div className="panel panel-pad h-100">
            <div className="small-label">Awaiting approval</div>
            <div className="stat-value" style={{ color: "var(--uc-warning)" }}>{pendingApprovals.length}</div>
            <div className="small-label mt-1">needs-approval actions</div>
          </div>
        </div>
        <div className="col-6 col-md-6 col-xl-3">
          <div className="panel panel-pad h-100">
            <div className="small-label">Early warnings</div>
            <div className="stat-value text-predict">{predictionsLoading && activePredictions.length === 0 ? "…" : activePredictions.length}</div>
            <div className="small-label mt-1">{predictionsLoading ? "scanning latest events…" : "predicted, not yet incidents"}</div>
          </div>
        </div>
      </div>

      <div className="row g-4">
        <div className="col-12 col-xl-7 min-w-0">
          <div className="section-title">
            <h6>Incidents</h6>
            <Link to="/incidents" className="small text-decoration-none">View all {incidents.length}</Link>
          </div>
          <div className="panel mb-4">
            {openIncidents.length === 0 ? (
              <div className="empty py-4">No incidents. Run an ingest or upload a SUMLOG.</div>
            ) : (
              openIncidents.map((inc) => <IncidentRow key={inc.incident_id} incident={inc} compact />)
            )}
          </div>

          {activePredictions.length > 0 && (
            <>
              <div className="section-title">
                <h6>Early warnings</h6>
                <Link to="/predictor" className="small text-decoration-none">View all</Link>
              </div>
              <div className="panel">
                {activePredictions.slice(0, 3).map((p) => (
                  <PredictionRow key={p.alert_id} prediction={p} showActions={false} />
                ))}
              </div>
            </>
          )}
        </div>

        <div className="col-12 col-xl-5 min-w-0">
          <div className="section-title">
            <h6>Awaiting your approval</h6>
          </div>
          <div className="panel mb-4">
            {pendingApprovals.length === 0 ? (
              <div className="empty py-4">Nothing waiting. Actions appear here after root cause analysis recommends them.</div>
            ) : (
              pendingApprovals.map((a) => (
                <Link key={`${a.incident_id}-${a.action_id}`} to={`/incidents/${a.incident_id}/actions`} className="row-link">
                  <div className="flex-grow-1 min-w-0">
                    <div className="fw-medium text-truncate" title={a.title}>{a.title}</div>
                    <div className="small-label d-flex flex-wrap align-items-center column-gap-2 mt-1">
                      <RiskBadge level={a.risk_level} />
                      <span className="font-mono">{a.action_id}</span>
                      <span className="font-mono">{a.incident_id}</span>
                    </div>
                  </div>
                  <i className="bi bi-chevron-right text-3 flex-shrink-0"></i>
                </Link>
              ))
            )}
          </div>

          <div className="section-title">
            <h6>Recent activity</h6>
            <Link to="/audit" className="small text-decoration-none">Audit log</Link>
          </div>
          <div className="panel">
            {audit.length === 0 ? (
              <div className="empty py-4">No audit entries yet.</div>
            ) : (
              audit.slice(0, 5).map((e) => (
                <div key={e.id} className="list-row">
                  <div className="d-flex align-items-center gap-2 min-w-0">
                    <DecisionBadge decision={e.decision} />
                    <span className="text-truncate" style={{ fontSize: "0.9rem" }} title={describeAudit(e, catalog)}>
                      {describeAudit(e, catalog)}
                    </span>
                  </div>
                  <div className="small-label mt-1">
                    #{e.id} · <span className="font-mono">{e.operator}</span> · {formatDateTime(e.timestamp)}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {confirmIngest && (
        <ConfirmModal
          title="Re-ingest the SUMLOG export?"
          confirmLabel="Run ingest"
          confirmClass="btn-danger"
          body={
            <>
              <p className="mb-2">
                This re-parses <span className="font-mono">data/sumlog_export.txt</span> and{" "}
                <strong>clears events, incidents, correlation results and cached root cause analyses</strong> before
                rebuilding them. Actions and the audit log are kept.
              </p>
              <p className="mb-0">Rebuilding a root cause analysis calls the LLM again and can take several minutes per incident.</p>
            </>
          }
          onConfirm={async () => {
            await runIngest();
            setConfirmIngest(false);
          }}
          onClose={() => setConfirmIngest(false)}
        />
      )}
    </div>
  );
};
