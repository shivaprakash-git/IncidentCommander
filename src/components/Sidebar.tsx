import React, { useEffect, useState } from "react";
import { NavLink, Link, Outlet, useLocation } from "react-router-dom";
import { useIncidents } from "../context/IncidentContext";
import { API_BASE_URL } from "../api";
import { CURRENT_OPERATOR } from "../lib/labels";
import { formatDateTime } from "../lib/format";

export const AppShell: React.FC = () => {
  const { incidents, activePredictions, pendingApprovals, health, backendOnline, ingesting, refresh } = useIncidents();
  const [open, setOpen] = useState(false);
  const location = useLocation();

  useEffect(() => setOpen(false), [location.pathname]);

  const linkClass = ({ isActive }: { isActive: boolean }) => `sidebar-link${isActive ? " active" : ""}`;

  return (
    <div className="shell">
      <aside className={`sidebar${open ? " open" : ""}`} aria-label="Main navigation">
        <Link to="/" className="sidebar-brand">
          <span className="brand-mark">
            <i className="bi bi-shield-check"></i>
          </span>
          Incident Commander
        </Link>

        <div className="sidebar-section">Overview</div>
        <NavLink to="/dashboard" className={linkClass}>
          <i className="bi bi-grid-1x2"></i>
          Dashboard
        </NavLink>

        <div className="sidebar-section">Operations</div>
        <NavLink to="/incidents" className={linkClass}>
          <i className="bi bi-diagram-3"></i>
          Incidents
          {pendingApprovals.length > 0 ? (
            <span className="sidebar-count" title="Actions awaiting approval">{pendingApprovals.length}</span>
          ) : (
            <span className="ms-auto small opacity-50">{incidents.length}</span>
          )}
        </NavLink>
        <NavLink to="/predictor" className={linkClass}>
          <i className="bi bi-graph-up-arrow"></i>
          Early warnings
          {activePredictions.length > 0 && (
            <span className="sidebar-count sidebar-count-predict">{activePredictions.length}</span>
          )}
        </NavLink>
        <NavLink to="/sumlog" className={linkClass}>
          <i className="bi bi-cloud-arrow-up"></i>
          Upload SUMLOG
        </NavLink>

        <div className="sidebar-section">Governance</div>
        <NavLink to="/audit" className={linkClass}>
          <i className="bi bi-journal-text"></i>
          Audit log
        </NavLink>

        <div className="sidebar-footer">
          {!backendOnline ? (
            <div className="mb-2" style={{ fontSize: "0.78rem" }}>
              <div className="d-flex align-items-center gap-2 text-white">
                <span className="status-dot" style={{ background: "var(--uc-critical)" }}></span>
                Backend offline
              </div>
              <div className="opacity-75 font-mono mt-1" style={{ wordBreak: "break-all" }}>{API_BASE_URL}</div>
            </div>
          ) : (
            <div className="mb-2">
              <div className="health-row">
                <span>Ingest</span>
                <span>{ingesting ? "running…" : health?.last_ingest_at ? formatDateTime(health.last_ingest_at) : "not recorded"}</span>
              </div>
              <div className="health-row">
                <span>Rule engine</span>
                <span className="text-truncate" title={health?.rule_engine_version}>
                  {health?.rule_engine_version.split(" ")[0] ?? "—"}
                </span>
              </div>
              <div className="health-row">
                <span>LLM</span>
                <span>{health ? (health.llm_configured ? "configured" : "not configured") : "—"}</span>
              </div>
              <div className="health-row">
                <span>Quantum solver</span>
                <span>{health?.quantum_solver ?? "—"}</span>
              </div>
            </div>
          )}
          <button
            type="button"
            className="btn btn-sm w-100 mb-2 text-white border-secondary border-opacity-50"
            style={{ background: "rgba(255,255,255,0.05)" }}
            onClick={() => void refresh()}
          >
            <i className="bi bi-arrow-clockwise me-1"></i>Refresh data
          </button>
          <div className="d-flex align-items-center gap-2 text-white pt-2 border-top border-secondary border-opacity-25">
            <i className="bi bi-person-circle fs-5"></i>
            <div className="lh-sm">
              <div className="font-mono" style={{ fontSize: "0.8rem" }}>{CURRENT_OPERATOR.id}</div>
              <div style={{ fontSize: "0.72rem", opacity: 0.6 }}>{CURRENT_OPERATOR.role}</div>
            </div>
          </div>
        </div>
      </aside>

      <div className={`sidebar-scrim${open ? " open" : ""}`} onClick={() => setOpen(false)}></div>

      <div className="content">
        <div className="mobile-bar">
          <button type="button" className="btn btn-light btn-sm" onClick={() => setOpen(true)} aria-label="Open navigation">
            <i className="bi bi-list fs-5"></i>
          </button>
          <span className="fw-semibold">Incident Commander</span>
        </div>
        {!backendOnline && (
          <div className="px-3 px-md-4 pt-3">
            <div className="banner-offline" role="alert">
              <i className="bi bi-plug"></i>
              <span>
                Cannot reach the backend at <span className="font-mono">{API_BASE_URL}</span>. Start it with{" "}
                <span className="font-mono">uvicorn api.main:app --port 8000</span>, then refresh.
              </span>
            </div>
          </div>
        )}
        <main>
          <Outlet />
        </main>
      </div>
    </div>
  );
};
