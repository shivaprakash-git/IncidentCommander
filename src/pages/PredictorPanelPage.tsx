import React, { useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { useIncidents } from "../context/IncidentContext";
import { api } from "../api";
import { predictionTitle } from "../components/Rows";
import { DismissReasonModal } from "../components/modals/DismissReasonModal";
import { Loading } from "../components/States";
import { TIMEZONE_LABEL, formatDuration, formatSpan, useApi } from "../lib/format";
import { humanFeature } from "../lib/labels";

const MODEL_LABEL: Record<string, string> = { qsvm: "QSVM (simulated)", svm_rbf: "SVM (RBF)", gbm: "Gradient boosting" };

export const PredictorPanelPage: React.FC = () => {
  const { patternId } = useParams<{ patternId: string }>();
  const { predictions, predictionsLoading, openPrediction, dismissPrediction } = useIncidents();
  const navigate = useNavigate();
  const qvc = useApi(() => api.quantumVsClassical(), []);
  const [dismissing, setDismissing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const back = (
    <Link to="/predictor" className="back-link">
      <i className="bi bi-arrow-left"></i> Early warnings
    </Link>
  );
  const p = predictions.find((x) => x.alert_id === patternId);

  if (!p && predictionsLoading) return <div className="page">{back}<Loading label="Scanning the latest events…" /></div>;
  if (!p) {
    return (
      <div className="page">
        {back}
        <div className="empty">
          <h5>This early warning is no longer in the latest scan</h5>
          <p className="mb-0">Newer events can merge or shift a matched window, which gives it a new ID.</p>
        </div>
      </div>
    );
  }

  const decided = p.status !== "active";
  const open = async () => {
    setBusy(true);
    setError(null);
    try {
      navigate(`/incidents/${await openPrediction(p.alert_id)}/timeline`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };

  return (
    <div className="page">
      {back}

      <div className="d-flex flex-column flex-md-row align-items-md-start justify-content-between gap-3 mb-4">
        <div className="min-w-0">
          <div className="d-flex flex-wrap gap-2 mb-2">
            <span className="pill pill-predict">Early warning</span>
            <span className="pill pill-neutral">Advisory — not an incident until opened</span>
            {decided && <span className="pill pill-neutral">{p.status === "opened" ? "Opened" : "Dismissed"}</span>}
          </div>
          <h4 className="mb-1">{predictionTitle(p)}</h4>
          <p className="small-label mb-0">
            <span className="font-mono">{p.alert_id}</span> · {p.subsystem} · matched window{" "}
            {formatSpan(p.window_start, p.window_end)} {TIMEZONE_LABEL}
          </p>
          {error && <div className="text-danger small mt-2">{error}</div>}
        </div>
        {!decided ? (
          <div className="d-flex gap-2 flex-shrink-0">
            <button type="button" className="btn btn-light" disabled={busy} onClick={() => setDismissing(true)}>Dismiss</button>
            <button type="button" className="btn btn-primary" disabled={busy} onClick={open}>
              {busy ? "Opening…" : "Open as incident"}
            </button>
          </div>
        ) : (
          p.incident_id && (
            <Link to={`/incidents/${p.incident_id}/timeline`} className="btn btn-outline-primary flex-shrink-0">
              Open {p.incident_id}
            </Link>
          )
        )}
      </div>

      <div className="row g-3 mb-3">
        <div className="col-6 col-md-3">
          <div className="panel panel-pad h-100">
            <div className="small-label">Similarity</div>
            <div className="stat-value text-predict">{p.similarity_score.toFixed(2)}</div>
            <div className="small-label">threshold 0.75</div>
          </div>
        </div>
        <div className="col-6 col-md-3">
          <div className="panel panel-pad h-100">
            <div className="small-label">Looks like</div>
            <div className="stat-value" style={{ fontSize: "1.3rem" }}>
              {p.matched_incident_id ? (
                <Link to={`/incidents/${p.matched_incident_id}/timeline`}>{p.matched_incident_id}</Link>
              ) : (
                "—"
              )}
            </div>
            <div className="small-label">lead-up of a past incident</div>
          </div>
        </div>
        <div className="col-6 col-md-3">
          <div className="panel panel-pad h-100">
            <div className="small-label">Matched events</div>
            <div className="stat-value">{p.matched_event_ids.length}</div>
            <div className="small-label">first 20 listed below</div>
          </div>
        </div>
        <div className="col-6 col-md-3">
          <div className="panel panel-pad h-100">
            <div className="small-label">Look-back window</div>
            <div className="stat-value">{formatDuration(p.nominal_lead_s)}</div>
            <div className="small-label">not a forecast of impact time</div>
          </div>
        </div>
      </div>

      <div className="panel panel-pad mb-3">
        <div className="small-label mb-2">Events that matched the pattern</div>
        <div className="d-flex flex-wrap gap-1">
          {p.matched_event_ids.map((id) => (
            <span key={id} className="pill pill-neutral font-mono">{id}</span>
          ))}
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          <h6 className="m-0">Model comparison (all labelled windows)</h6>
          {qvc.data && <span className="small-label">{qvc.data.n_positive} incidents · {qvc.data.n_negative} normal windows</span>}
        </div>
        {qvc.loading ? (
          <Loading />
        ) : qvc.error || !qvc.data ? (
          <div className="empty py-4">No quantum-vs-classical result has been produced yet.</div>
        ) : (
          <>
            <div className="table-responsive">
              <table className="table m-0 align-middle" style={{ fontSize: "0.88rem" }}>
                <thead>
                  <tr>
                    <th className="ps-4 small-label fw-medium">Model</th>
                    <th className="small-label fw-medium">Precision</th>
                    <th className="small-label fw-medium">Recall</th>
                    <th className="pe-4 small-label fw-medium">AUC</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(qvc.data.results).map(([model, m]) => (
                    <tr key={model}>
                      <td className="ps-4">{MODEL_LABEL[model] ?? model}</td>
                      {[m.precision, m.recall, m.auc].map((s, i) => (
                        <td key={i} className={`font-mono${i === 2 ? " pe-4" : ""}`}>
                          {s.mean.toFixed(2)} <span className="text-3">± {s.std.toFixed(2)}</span>
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="panel-foot small-label d-block">
              Features: {qvc.data.features.map(humanFeature).join(", ")} · {qvc.data.cv}.
              {qvc.data.note && <> {qvc.data.note}.</>} Classical models are as good or better here; no quantum advantage is claimed.
            </div>
          </>
        )}
      </div>

      {dismissing && (
        <DismissReasonModal
          patternId={p.alert_id}
          onConfirm={async (reason) => {
            await dismissPrediction(p.alert_id, reason);
            navigate("/predictor");
          }}
          onClose={() => setDismissing(false)}
        />
      )}
    </div>
  );
};
