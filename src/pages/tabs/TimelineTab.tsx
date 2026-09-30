import React, { useState } from "react";
import { Link, useOutletContext, useSearchParams } from "react-router-dom";
import type { TimelineEntry, TimelineRole } from "../../types";
import { api } from "../../api";
import { SeverityBadge } from "../../components/SeverityBadge";
import { Loading, ErrorState } from "../../components/States";
import { formatDuration, formatTime, formatTimeSec, secondsBetween, useApi } from "../../lib/format";
import { humanType } from "../../lib/labels";
import type { IncidentOutlet } from "../IncidentDetailPage";

const PHASES: TimelineRole[] = ["trigger", "propagation", "symptom"];
const VISIBLE_PROPAGATION = 4;

const PHASE_META: Record<TimelineRole | "precursor", { label: string; icon: string; dot: string }> = {
  precursor: { label: "precursor window", icon: "bi-graph-up-arrow", dot: "var(--uc-predict)" },
  trigger: { label: "trigger", icon: "bi-lightning-charge", dot: "var(--uc-critical)" },
  propagation: { label: "propagation", icon: "bi-diagram-2", dot: "var(--uc-warning)" },
  symptom: { label: "symptom", icon: "bi-person-exclamation", dot: "var(--uc-teal)" },
};

const ms = (iso: string) => new Date(iso).getTime();
// Naive timestamps parse as browser-local time, so format back in local time to avoid any shift.
const isoOf = (t: number) => {
  const d = new Date(t);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
};

interface Segment {
  key: TimelineRole | "precursor";
  start: number;
  end: number;
  dots: number[];
}

export const TimelineTab: React.FC = () => {
  const { incident } = useOutletContext<IncidentOutlet>();
  const [params] = useSearchParams();
  const linked = params.get("event");
  const tl = useApi(() => api.timeline(incident.incident_id), [incident.incident_id]);
  const ew = useApi(() => api.earlyWarning(incident.incident_id), [incident.incident_id]);
  const [showAll, setShowAll] = useState(false);
  const [openId, setOpenId] = useState<string | null>(linked);

  if (tl.loading) return <div className="panel"><Loading label="Building timeline (correlating the incident window)…" /></div>;
  if (tl.error || !tl.data) return <div className="panel"><ErrorState error={tl.error ?? new Error("No timeline")} onRetry={() => void tl.reload()} /></div>;

  const { timeline, cluster_size, correlation } = tl.data;
  const entries = [...timeline.entries].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  const grouped: Record<TimelineRole, TimelineEntry[]> = { trigger: [], propagation: [], symptom: [] };
  entries.forEach((e) => grouped[e.role].push(e));

  // Always show salient propagation events (non-INFO, anchor, linked); fold the routine rest.
  const salient = (e: TimelineEntry) => e.severity !== "INFO" || e.is_anchor || e.event_id === linked;
  const visibleProp = showAll
    ? grouped.propagation
    : grouped.propagation.filter((e, i) => i < VISIBLE_PROPAGATION || salient(e));
  const hiddenCount = grouped.propagation.length - visibleProp.length;

  const precursor = ew.data?.alerts[0];
  const triggerIso = grouped.trigger[0]?.timestamp ?? timeline.start ?? incident.trigger_ts;
  const triggerT = ms(triggerIso);
  const endT = timeline.end ? ms(timeline.end) : triggerT;
  const leadS = precursor ? Math.max(0, Math.round((ms(incident.trigger_ts) - ms(precursor.window_end)) / 1000)) : null;
  const entities = new Set(entries.map((e) => e.job_id).filter(Boolean)).size;

  const segments: Segment[] = [];
  if (precursor) segments.push({ key: "precursor", start: ms(precursor.window_start), end: triggerT, dots: [] });
  const starts = PHASES.map((p) => (grouped[p][0] ? ms(grouped[p][0].timestamp) : undefined));
  PHASES.forEach((phase, i) => {
    const start = starts[i];
    if (start === undefined) return;
    const end = starts.slice(i + 1).find((s) => s !== undefined) ?? endT;
    segments.push({ key: phase, start, end, dots: grouped[phase].map((e) => ms(e.timestamp)) });
  });
  const total = Math.max((segments.at(-1)?.end ?? endT) - (segments[0]?.start ?? triggerT), 1);
  const grow = (s: Segment) => Math.max(s.end - s.start, total * 0.12);
  const dotLeft = (s: Segment, t: number) => Math.min(94, Math.max(6, ((t - s.start) / Math.max(s.end - s.start, 1)) * 100));
  // Thin dots when a phase has many events, so the bar stays readable.
  const sampleDots = (dots: number[]) => (dots.length > 40 ? dots.filter((_, i) => i % Math.ceil(dots.length / 40) === 0) : dots);

  const renderEntry = (e: TimelineEntry) => {
    const isOpen = openId === e.event_id;
    return (
      <React.Fragment key={e.event_id}>
        <button
          type="button"
          className={`tl-row${e.role === "trigger" ? " tl-row-trigger" : ""}${e.event_id === linked ? " tl-row-linked" : ""}`}
          onClick={() => setOpenId(isOpen ? null : e.event_id)}
          aria-expanded={isOpen}
        >
          <span className="tl-time">{formatTimeSec(e.timestamp)}</span>
          <span className="tl-id">{e.event_id}</span>
          <span className="tl-msg text-truncate" title={e.summary}>
            {e.is_anchor && <span className="pill pill-predict me-2">discovery hit</span>}
            <span className="tl-entity me-2">{e.keyword}</span>
            {e.summary}
          </span>
          <span className="tl-badge"><SeverityBadge severity={e.severity} /></span>
        </button>
        {isOpen && (
          <div className="tl-detail">
            <div className="small-label mb-2">
              {e.timestamp.replace("T", " ")} · keyword {e.keyword} · job {e.job_id ?? "—"} · role {e.role}
              {e.is_anchor && " · the keyword hit that opened this incident"}
            </div>
            <pre className="code-block font-mono">{e.summary.split(" | ").join("\n")}</pre>
          </div>
        )}
      </React.Fragment>
    );
  };

  const phaseHeader = (phase: TimelineRole | "precursor", text: React.ReactNode) => (
    <div className={`tl-phase-head tl-head-${phase}`}>
      <i className={`bi ${PHASE_META[phase].icon}`} aria-hidden="true"></i>
      {text}
    </div>
  );

  return (
    <div className="panel overflow-hidden">
      <div className="panel-pad">
        <div className="row g-3 mb-4">
          <div className="col-6 col-lg-3">
            <div className="tl-card">
              <div className="small-label">Time span</div>
              <div className="stat-value font-mono">{formatTime(timeline.start)}–{formatTime(timeline.end)}</div>
              <div className="small-label">{formatDuration(timeline.duration_s)}</div>
            </div>
          </div>
          <div className="col-6 col-lg-3">
            <div className="tl-card">
              <div className="small-label">Events in this cluster</div>
              <div className="stat-value">{cluster_size.toLocaleString()}</div>
              <div className="small-label">of {correlation.n_events.toLocaleString()} in the window</div>
            </div>
          </div>
          <div className="col-6 col-lg-3">
            <div className="tl-card">
              <div className="small-label">Entities (jobs)</div>
              <div className="stat-value">{entities}</div>
              <div className="small-label">{correlation.n_clusters} clusters in window</div>
            </div>
          </div>
          <div className="col-6 col-lg-3">
            <div className="tl-card">
              <div className="small-label">Early warning</div>
              {ew.loading ? (
                <div className="stat-value text-3">…</div>
              ) : leadS !== null ? (
                <>
                  <div className="stat-value text-predict">{leadS < 60 ? `${leadS} s` : `${Math.round(leadS / 60)} min`} lead</div>
                  <div className="small-label">similarity {precursor!.similarity_score.toFixed(2)}</div>
                </>
              ) : (
                <div className="stat-value text-3">None</div>
              )}
            </div>
          </div>
        </div>

        <div className="phase-track" aria-hidden="true">
          {segments.map((s) => (
            <div key={s.key} className={`phase-seg phase-seg-${s.key}`} style={{ flexGrow: grow(s), flexBasis: 0 }}>
              {sampleDots(s.dots).map((t, i) => (
                <span key={i} className="phase-dot" style={{ left: `${dotLeft(s, t)}%`, background: PHASE_META[s.key].dot }}></span>
              ))}
            </div>
          ))}
        </div>
        <div className="phase-labels">
          {segments.map((s, i) => (
            <div
              key={s.key}
              style={{ flexGrow: grow(s), flexBasis: 0 }}
              className={i === segments.length - 1 ? "d-flex justify-content-between gap-2" : undefined}
            >
              <span className="text-truncate">{formatTimeSec(isoOf(s.start))} {PHASE_META[s.key].label}</span>
              {i === segments.length - 1 && <span>{formatTimeSec(isoOf(s.end))}</span>}
            </div>
          ))}
        </div>
      </div>

      {precursor && (
        <>
          {phaseHeader(
            "precursor",
            <>Precursor · early-warning pattern matched {leadS !== null && leadS < 60 ? `${leadS} s` : `${Math.round((leadS ?? 0) / 60)} min`} before trigger</>
          )}
          <div className="tl-row">
            <span className="tl-time">{formatTimeSec(precursor.window_end)}</span>
            <span className="tl-id">{precursor.matched_event_ids.length} events</span>
            <span className="tl-msg text-truncate" title={humanType(precursor.matched_incident_type)}>
              {humanType(precursor.matched_incident_type)} pattern
              {precursor.matched_incident_id && (
                <>
                  {" "}like <Link to={`/incidents/${precursor.matched_incident_id}/timeline`}>{precursor.matched_incident_id}</Link>
                </>
              )}
              <span className="text-3"> · window {formatTimeSec(precursor.window_start)}–{formatTimeSec(precursor.window_end)}</span>
            </span>
            <span className="tl-badge"><span className="pill pill-predict">Advisory</span></span>
          </div>
        </>
      )}

      {grouped.trigger.length > 0 && (
        <>
          {phaseHeader("trigger", "Trigger · first event of the correlated cluster")}
          {grouped.trigger.map(renderEntry)}
        </>
      )}

      {grouped.propagation.length > 0 && (
        <>
          {phaseHeader("propagation", <>Propagation · {grouped.propagation.length} events</>)}
          {visibleProp.map(renderEntry)}
          {(hiddenCount > 0 || showAll) && (
            <button type="button" className="tl-more" onClick={() => setShowAll((v) => !v)}>
              <i className={`bi bi-chevron-${showAll ? "up" : "down"} me-2`}></i>
              {showAll ? "Show fewer" : `${hiddenCount} more routine events`}
            </button>
          )}
        </>
      )}

      {grouped.symptom.length > 0 && (
        <>
          {phaseHeader("symptom", "Symptom · most severe late event")}
          {grouped.symptom.map(renderEntry)}
        </>
      )}

      <div className="tl-footer">
        <span className="small-label">
          Phases come from the timeline builder (causal order in the trigger's Louvain cluster), not the LLM.{" "}
          {secondsBetween(timeline.start ?? triggerIso, timeline.end ?? triggerIso) === 0 && "All events share one timestamp."}
        </span>
        <Link to={`/incidents/${incident.incident_id}/rca`} className="btn btn-outline-primary btn-sm">
          Next: see root cause <i className="bi bi-arrow-up-right ms-1"></i>
        </Link>
      </div>
    </div>
  );
};
