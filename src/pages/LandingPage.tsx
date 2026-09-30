import React from "react";
import { Link } from "react-router-dom";
import { useIncidents } from "../context/IncidentContext";

const features = [
  {
    icon: "bi-diagram-3",
    title: "Group the noise",
    text: "Thousands of raw mainframe alerts are correlated into a handful of incidents.",
  },
  {
    icon: "bi-search",
    title: "Explain the cause",
    text: "Ranked root-cause hypotheses, each backed by cited events and runbooks.",
  },
  {
    icon: "bi-shield-check",
    title: "Act safely",
    text: "A rule engine sets every action's risk. Nothing changes without your approval.",
  },
];

export const LandingPage: React.FC = () => {
  const { summary, activePredictions, predictionsLoading } = useIncidents();

  return (
    <div className="min-vh-100 d-flex flex-column">
      <header className="d-flex align-items-center justify-content-between px-3 px-md-4 py-3" style={{ maxWidth: 1100, width: "100%", margin: "0 auto" }}>
        <div className="d-flex align-items-center gap-2">
          <span className="brand-mark">
            <i className="bi bi-shield-check"></i>
          </span>
          <span className="fw-semibold">Incident Commander</span>
        </div>
        <Link to="/dashboard" className="btn btn-sm btn-outline-primary">
          Dashboard
        </Link>
      </header>

      <section className="hero">
        <span className="pill pill-info mb-3">For ClearPath MCP operations</span>
        <h1 className="mb-3">Calm, clear incident triage for your mainframe.</h1>
        <p className="text-2 fs-5 mb-4">
          See what's broken, why it broke, and what to do next — with a human in control of every change.
        </p>
        <div className="d-flex flex-wrap justify-content-center gap-2">
          <Link to="/dashboard" className="btn btn-primary btn-lg px-4">
            Open dashboard <i className="bi bi-arrow-right ms-1"></i>
          </Link>
          <Link to="/audit" className="btn btn-link btn-lg text-decoration-none">
            View audit log
          </Link>
        </div>

        <div className="panel panel-pad d-inline-flex flex-wrap justify-content-center gap-4 mt-5 text-start">
          <div>
            <div className="small-label">Alerts (warn + critical)</div>
            <div className="stat-value">{summary?.alerts ?? "—"}</div>
          </div>
          <i className="bi bi-arrow-right align-self-center text-3 fs-4"></i>
          <div>
            <div className="small-label">Incidents</div>
            <div className="stat-value" style={{ color: "var(--uc-teal)" }}>{summary?.incidents ?? "—"}</div>
          </div>
          <div className="vr d-none d-sm-block"></div>
          <div>
            <div className="small-label">Early warnings</div>
            <div className="stat-value text-predict">{predictionsLoading && activePredictions.length === 0 ? "…" : activePredictions.length}</div>
          </div>
        </div>
      </section>

      <section className="px-3 pb-5" style={{ maxWidth: 1000, margin: "0 auto", width: "100%" }}>
        <div className="row g-3">
          {features.map((f) => (
            <div key={f.title} className="col-12 col-md-4">
              <div className="panel panel-pad h-100">
                <span className="feature-icon mb-3">
                  <i className={`bi ${f.icon}`}></i>
                </span>
                <h6 className="mb-1">{f.title}</h6>
                <p className="text-2 mb-0" style={{ fontSize: "0.9rem" }}>{f.text}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <footer className="mt-auto text-center text-3 py-4" style={{ fontSize: "0.8rem" }}>
        AI suggests. Rules classify. Humans decide.
      </footer>
    </div>
  );
};
