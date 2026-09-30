import React, { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { api } from "../../api";
import { Loading, ErrorState } from "../../components/States";
import { useApi, useElapsed } from "../../lib/format";
import type { IncidentOutlet } from "../IncidentDetailPage";

const fmtS = (s?: number) => (s === undefined ? "—" : s < 1 ? `${Math.round(s * 1000)} ms` : `${s.toFixed(1)} s`);

export const ComparisonTab: React.FC = () => {
  const { incident } = useOutletContext<IncidentOutlet>();
  const corr = useApi(() => api.correlation(incident.incident_id), [incident.incident_id]);
  const [runningQuantum, setRunningQuantum] = useState(false);
  const [quantumError, setQuantumError] = useState<string | null>(null);
  const elapsed = useElapsed(runningQuantum);

  const runQuantum = async () => {
    setRunningQuantum(true);
    setQuantumError(null);
    try {
      corr.setData(await api.correlation(incident.incident_id, true));
    } catch (e) {
      setQuantumError((e as Error).message);
    } finally {
      setRunningQuantum(false);
    }
  };

  if (corr.loading) return <div className="panel"><Loading label="Correlating the incident window (Louvain)…" /></div>;
  if (corr.error || !corr.data) return <div className="panel"><ErrorState error={corr.error ?? new Error("No result")} onRetry={() => void corr.reload()} /></div>;

  const c = corr.data;
  const q = c.quantum;
  const ran = q.status !== "skipped";
  const rows: { label: string; classical: string; quantum: string }[] = [
    { label: "Method", classical: "Louvain community detection", quantum: "QAOA min-cut on a QUBO (simulator)" },
    { label: "Events", classical: c.n_events.toLocaleString(), quantum: q.n_qubits ? `${q.n_qubits}-event subsample` : "—" },
    { label: "Clusters", classical: String(c.classical.n_clusters), quantum: ran ? "2 (min-cut)" : "—" },
    { label: "Runtime", classical: fmtS(c.classical.runtime_s), quantum: fmtS(q.runtime_s) },
    { label: "Status", classical: "ok", quantum: q.status + (q.reason ? ` (${q.reason})` : "") },
  ];

  return (
    <>
      <div className="panel overflow-hidden">
        <table className="table m-0 align-middle" style={{ fontSize: "0.9rem" }}>
          <thead>
            <tr>
              <th className="ps-4 small-label fw-medium"></th>
              <th className="small-label fw-medium">Classical</th>
              <th className="pe-4 small-label fw-medium">Quantum (simulated)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.label}>
                <td className="ps-4 text-2">{r.label}</td>
                <td>{r.classical}</td>
                <td className="pe-4">{r.quantum}</td>
              </tr>
            ))}
            <tr>
              <td className="ps-4 text-2">Agreement (ARI)</td>
              <td colSpan={2}>
                {c.ari === null ? <span className="text-3">Needs a quantum run</span> : c.ari.toFixed(3)}
                <span className="small-label ms-2">1 = identical grouping, 0 = chance</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="d-flex flex-wrap align-items-center justify-content-between gap-2 mt-3">
        <div className="small-label" style={{ maxWidth: 640 }}>
          Reported as measured. Louvain on the full window is what the timeline uses; QAOA runs on a small subsample
          and is compared with Louvain on the same events. At this scale classical matches or beats it, so this shows a
          working hybrid path, not a quantum advantage.
          {c.notes.map((n) => <div key={n}>{n}</div>)}
        </div>
        {!ran && (
          <button type="button" className="btn btn-sm btn-outline-primary" disabled={runningQuantum} onClick={runQuantum}>
            {runningQuantum ? (
              <>
                <span className="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>Running QAOA… {elapsed}s
              </>
            ) : (
              "Run quantum comparison"
            )}
          </button>
        )}
      </div>
      {quantumError && <div className="text-danger small mt-2">{quantumError}</div>}
    </>
  );
};
