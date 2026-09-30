import React, { useState } from "react";
import { useIncidents } from "../context/IncidentContext";
import { PredictionRow } from "../components/Rows";
import { Loading, ErrorState } from "../components/States";
import { TIMEZONE_LABEL } from "../lib/format";

export const PredictorListPage: React.FC = () => {
  const { predictions, activePredictions, predictionsLoading, error, refresh } = useIncidents();
  const [showDecided, setShowDecided] = useState(false);
  const decided = predictions.filter((p) => p.status !== "active");
  const list = showDecided ? predictions : activePredictions;

  return (
    <div className="page">
      <div className="page-header">
        <h4>Early warnings</h4>
        <p className="text-2 mb-2">
          The latest events compared against the lead-up of past incidents. Times are {TIMEZONE_LABEL}.
        </p>
        <span className="pill pill-predict">
          <i className="bi bi-info-circle"></i>
          Advisory — not an incident until opened
        </span>
      </div>

      {decided.length > 0 && (
        <div className="form-check form-switch mb-3">
          <input
            className="form-check-input"
            type="checkbox"
            role="switch"
            id="show-decided"
            checked={showDecided}
            onChange={(e) => setShowDecided(e.target.checked)}
          />
          <label className="form-check-label small" htmlFor="show-decided">
            Show dismissed and opened ({decided.length})
          </label>
        </div>
      )}

      <div className="panel">
        {predictionsLoading && predictions.length === 0 ? (
          <Loading label="Scanning the latest events for early-warning patterns…" />
        ) : error && predictions.length === 0 ? (
          <ErrorState error={error} onRetry={() => void refresh()} />
        ) : list.length === 0 ? (
          <div className="empty">No active early warnings in the latest 60 minutes of events.</div>
        ) : (
          list.map((p) => <PredictionRow key={p.alert_id} prediction={p} />)
        )}
      </div>
      <p className="small-label mt-2 mb-0">
        Similarity is a cosine match of anomaly-feature counts against known pre-incident windows (threshold 0.75). It is
        not a trained classifier and does not forecast a time to impact.
      </p>
    </div>
  );
};
