import React, { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useIncidents } from "../context/IncidentContext";
import { api, uploadSumlog } from "../api";
import { Loading } from "../components/States";
import { formatBytes, formatDateTime, formatSpan, useApi } from "../lib/format";
import { CURRENT_OPERATOR, humanType } from "../lib/labels";
import type { UploadResult } from "../types";

// Must match engine/uploads.py (ACCEPTED_EXTENSIONS, UPLOAD_MAX_BYTES default).
const ACCEPTED = [".log", ".txt", ".csv", ".sum"];
const MAX_BYTES = 50 * 1024 * 1024;
const PREVIEW_BYTES = 2 * 1024 * 1024;
// LOGANALYZER record headers: "   23:59:00    BOJ ...", "23:59:02.5271  TIME ...", "08/14/2023 10:31:31.1234 ..."
const RECORD_HEADER = /^(\s{0,3}\d{2}:\d{2}:\d{2}(\.\d+)?\s|\d{2}\/\d{2}\/\d{4} \d{2}:\d{2}:\d{2})/;

type Status = "reading" | "ready" | "uploading" | "sent" | "error";

interface QueuedFile {
  id: string;
  file: File;
  status: Status;
  progress: number;
  estimate: number;
  estimated: boolean;
  preview: string[];
  error?: string;
  result?: UploadResult;
  showPreview: boolean;
}

const STATUS_PILL: Record<Status, { cls: string; text: string }> = {
  reading: { cls: "pill-neutral", text: "Reading…" },
  ready: { cls: "pill-info", text: "Ready" },
  uploading: { cls: "pill-info", text: "Uploading" },
  sent: { cls: "pill-safe", text: "Ingested" },
  error: { cls: "pill-critical", text: "Failed" },
};

const extOf = (name: string) => (name.includes(".") ? name.slice(name.lastIndexOf(".")).toLowerCase() : "");

async function inspect(file: File): Promise<Partial<QueuedFile>> {
  if (!ACCEPTED.includes(extOf(file.name))) return { status: "error", error: `Unsupported file type. Use ${ACCEPTED.join(", ")}.` };
  if (file.size === 0) return { status: "error", error: "The file is empty." };
  if (file.size > MAX_BYTES) return { status: "error", error: `File is ${formatBytes(file.size)}; the limit is ${formatBytes(MAX_BYTES)}.` };
  const text = await file.slice(0, PREVIEW_BYTES).text();
  const lines = text.split(/\r?\n/);
  const headers = lines.filter((l) => RECORD_HEADER.test(l)).length;
  if (headers === 0) {
    return { status: "error", error: "No SUMLOG records found. Expected a LOGANALYZER text export." };
  }
  const estimated = file.size > PREVIEW_BYTES;
  return {
    status: "ready",
    estimate: estimated ? Math.round((headers * file.size) / PREVIEW_BYTES) : headers,
    estimated,
    preview: lines.filter((l) => l.trim()).slice(0, 14),
  };
}

export const SumlogUploadPage: React.FC = () => {
  const { incidents, refresh } = useIncidents();
  const uploads = useApi(() => api.uploads(10), []);
  const inputRef = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);
  const [dragging, setDragging] = useState(false);
  const [queue, setQueue] = useState<QueuedFile[]>([]);
  const [host, setHost] = useState("");
  const [attachTo, setAttachTo] = useState("");
  const [sending, setSending] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const update = (id: string, patch: Partial<QueuedFile>) => setQueue((q) => q.map((f) => (f.id === id ? { ...f, ...patch } : f)));

  const addFiles = (files: File[]) => {
    const fresh: QueuedFile[] = [];
    let duplicates = 0;
    for (const file of files) {
      if ([...queue, ...fresh].some((f) => f.file.name === file.name && f.file.size === file.size)) {
        duplicates++;
        continue;
      }
      fresh.push({
        id: `${file.name}-${file.size}-${Math.random().toString(36).slice(2, 8)}`,
        file,
        status: "reading",
        progress: 0,
        estimate: 0,
        estimated: false,
        preview: [],
        showPreview: false,
      });
    }
    setNotice(duplicates ? `Skipped ${duplicates} file${duplicates > 1 ? "s" : ""} already in the list.` : null);
    setQueue((q) => [...q, ...fresh]);
    fresh.forEach((f) => inspect(f.file).then((patch) => update(f.id, patch)));
  };

  const ready = queue.filter((f) => f.status === "ready");
  const sent = queue.filter((f) => f.status === "sent");
  const created = sent.flatMap((f) => f.result?.incidents_created ?? []);

  const send = async () => {
    setSending(true);
    setNotice(null);
    for (const f of ready) {
      update(f.id, { status: "uploading", progress: 0, showPreview: false, error: undefined });
      try {
        const result = await uploadSumlog(
          f.file,
          { host: host.trim(), operator: CURRENT_OPERATOR.id, attachTo: attachTo || undefined },
          (pct) => update(f.id, { progress: pct })
        );
        update(f.id, { status: "sent", progress: 100, result });
      } catch (e) {
        update(f.id, { status: "error", error: (e as Error).message });
      }
    }
    setSending(false);
    void uploads.reload();
    void refresh();
  };

  return (
    <div className="page">
      <div className="page-header">
        <h4>Upload SUMLOG</h4>
        <p className="text-2 mb-0">
          Add LOGANALYZER text exports from an MCP host. The backend parses them, discovers incident windows and adds
          them to Incidents.
        </p>
      </div>

      <div className="row g-4">
        <div className="col-12 col-lg-8 min-w-0 d-flex flex-column gap-4">
          <div className="panel panel-pad">
            <div
              className={`dropzone${dragging ? " is-dragging" : ""}`}
              onDragEnter={(e) => {
                e.preventDefault();
                dragDepth.current++;
                setDragging(true);
              }}
              onDragOver={(e) => e.preventDefault()}
              onDragLeave={() => {
                dragDepth.current = Math.max(0, dragDepth.current - 1);
                if (dragDepth.current === 0) setDragging(false);
              }}
              onDrop={(e) => {
                e.preventDefault();
                dragDepth.current = 0;
                setDragging(false);
                addFiles(Array.from(e.dataTransfer.files));
              }}
            >
              <span className="dz-icon">
                <i className="bi bi-cloud-arrow-up"></i>
              </span>
              <div className="fw-semibold mt-3">{dragging ? "Drop to add files" : "Drag SUMLOG exports here"}</div>
              <div className="small-label mt-1">{ACCEPTED.join(", ")} · up to {formatBytes(MAX_BYTES)} each</div>
              <button type="button" className="btn btn-primary btn-sm mt-3" onClick={() => inputRef.current?.click()}>
                Browse files
              </button>
              <input
                ref={inputRef}
                id="sumlog-files"
                type="file"
                multiple
                accept={ACCEPTED.join(",")}
                className="d-none"
                onChange={(e) => {
                  addFiles(Array.from(e.target.files ?? []));
                  e.target.value = "";
                }}
              />
            </div>

            <div className="row g-3 mt-2">
              <div className="col-12 col-md-6">
                <label htmlFor="sumlog-host" className="form-label small-label mb-1">Source host (optional)</label>
                <input
                  id="sumlog-host"
                  className="form-control form-control-sm"
                  placeholder="e.g. the MCP system name"
                  value={host}
                  disabled={sending}
                  onChange={(e) => setHost(e.target.value)}
                />
              </div>
              <div className="col-12 col-md-6">
                <label htmlFor="sumlog-attach" className="form-label small-label mb-1">Correlation</label>
                <select
                  id="sumlog-attach"
                  className="form-select form-select-sm"
                  value={attachTo}
                  disabled={sending}
                  onChange={(e) => setAttachTo(e.target.value)}
                >
                  <option value="">Discover new incidents (recommended)</option>
                  {incidents.map((i) => (
                    <option key={i.incident_id} value={i.incident_id}>
                      Attach to {i.incident_id} · {humanType(i.type)}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {notice && (
            <div className="small-label d-flex align-items-center gap-2">
              <i className="bi bi-info-circle"></i>
              {notice}
            </div>
          )}

          {sent.length > 0 && !sending && (
            <div className="banner-success" role="status">
              <i className="bi bi-check-circle fs-5"></i>
              <div className="flex-grow-1 min-w-0">
                <strong>{sent.length} file{sent.length > 1 ? "s" : ""} ingested.</strong>{" "}
                {created.length > 0
                  ? `${created.length} new incident${created.length > 1 ? "s" : ""} discovered.`
                  : attachTo
                    ? `Events attached to ${attachTo}.`
                    : "No incident windows were found in the uploaded records."}
              </div>
              {created.length > 0 ? (
                <Link to={`/incidents/${created[0]}/timeline`} className="btn btn-sm btn-outline-primary flex-shrink-0">Open {created[0]}</Link>
              ) : (
                <Link to={attachTo ? `/incidents/${attachTo}/timeline` : "/incidents"} className="btn btn-sm btn-outline-primary flex-shrink-0">
                  {attachTo ? `Open ${attachTo}` : "View incidents"}
                </Link>
              )}
            </div>
          )}

          <div className="panel">
            <div className="panel-head">
              <h6 className="m-0">Files {queue.length > 0 && <span className="text-3 fw-normal">({queue.length})</span>}</h6>
              {queue.length > 0 && !sending && (
                <button type="button" className="btn btn-link btn-sm p-0 text-decoration-none" onClick={() => { setQueue([]); setNotice(null); }}>
                  Clear list
                </button>
              )}
            </div>

            {queue.length === 0 ? (
              <div className="empty py-5">
                <i className="bi bi-file-earmark-text fs-3 d-block mb-2 text-3"></i>
                No files yet. Add a SUMLOG export above to preview it before sending.
              </div>
            ) : (
              queue.map((f) => {
                const pill = STATUS_PILL[f.status];
                const r = f.result;
                return (
                  <div key={f.id} className="file-row">
                    <span className={`file-icon${f.status === "error" ? " is-error" : ""}`}>
                      <i className={`bi ${f.status === "sent" ? "bi-check2" : "bi-file-earmark-text"}`}></i>
                    </span>
                    <div className="flex-grow-1 min-w-0">
                      <div className="d-flex align-items-center justify-content-between gap-2">
                        <span className="fw-medium text-truncate" title={f.file.name}>{f.file.name}</span>
                        <span className={`pill ${pill.cls} flex-shrink-0`}>
                          {pill.text}
                          {f.status === "uploading" && ` ${f.progress}%`}
                        </span>
                      </div>
                      <div className="small-label d-flex flex-wrap column-gap-2 mt-1">
                        <span>{formatBytes(f.file.size)}</span>
                        {r ? (
                          <>
                            <span>{r.records.toLocaleString()} records parsed</span>
                            <span>{formatSpan(r.first_ts, r.last_ts)}</span>
                            <span className="font-mono">{r.batch_id}</span>
                          </>
                        ) : (
                          f.status !== "error" && f.status !== "reading" && (
                            <span>{f.estimated ? "≈ " : ""}{f.estimate.toLocaleString()} records (preview count)</span>
                          )
                        )}
                      </div>
                      {r && r.incidents_created.length > 0 && (
                        <div className="small-label mt-1">
                          New incidents:{" "}
                          {r.incidents_created.map((id, i) => (
                            <React.Fragment key={id}>
                              {i > 0 && ", "}
                              <Link to={`/incidents/${id}/timeline`} className="font-mono">{id}</Link>
                            </React.Fragment>
                          ))}
                        </div>
                      )}
                      {r && r.attach_to && (
                        <div className="small-label mt-1">
                          {r.events_in_attached_window ?? 0} of {r.records} records fall inside {r.attach_to}'s window
                          {r.events_in_attached_window === 0 && " (they will not show on its timeline)"}.
                        </div>
                      )}

                      {f.status === "uploading" && (
                        <div className="progress-thin mt-2" role="progressbar" aria-valuenow={f.progress} aria-valuemin={0} aria-valuemax={100}>
                          <div style={{ width: `${f.progress}%` }}></div>
                        </div>
                      )}
                      {f.error && <div className="text-danger mt-1" style={{ fontSize: "0.85rem" }}>{f.error}</div>}

                      {f.preview.length > 0 && f.status !== "uploading" && (
                        <>
                          <button
                            type="button"
                            className="btn btn-link btn-sm p-0 mt-1 text-decoration-none"
                            onClick={() => update(f.id, { showPreview: !f.showPreview })}
                            aria-expanded={f.showPreview}
                          >
                            {f.showPreview ? "Hide preview" : "Preview first lines"}
                          </button>
                          {f.showPreview && <pre className="code-block font-mono mt-2 mb-0 sumlog-preview">{f.preview.join("\n")}</pre>}
                        </>
                      )}
                    </div>
                    {(f.status === "ready" || f.status === "error") && !sending && (
                      <button
                        type="button"
                        className="btn btn-sm btn-light file-remove flex-shrink-0"
                        aria-label={`Remove ${f.file.name}`}
                        onClick={() => setQueue((q) => q.filter((x) => x.id !== f.id))}
                      >
                        <i className="bi bi-x-lg"></i>
                      </button>
                    )}
                  </div>
                );
              })
            )}

            {queue.length > 0 && (
              <div className="panel-foot">
                <span className="small-label">
                  {ready.length > 0 ? `${ready.length} file${ready.length > 1 ? "s" : ""} ready` : sending ? "Uploading…" : "Nothing ready to send"}
                </span>
                <button type="button" className="btn btn-primary btn-sm" disabled={ready.length === 0 || sending} onClick={send}>
                  {sending ? (
                    <>
                      <span className="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>Sending
                    </>
                  ) : (
                    "Send to ingest"
                  )}
                </button>
              </div>
            )}
          </div>
        </div>

        <div className="col-12 col-lg-4 min-w-0 d-flex flex-column gap-4">
          <div className="panel panel-pad">
            <h6 className="mb-3">What happens next</h6>
            <ol className="steps">
              <li><span className="step-n">1</span><div><strong>Upload</strong><span>The file is stored on the backend with a batch ID.</span></div></li>
              <li><span className="step-n">2</span><div><strong>Parse</strong><span>Each SUMLOG record becomes an event; IDs are batch-prefixed so nothing is overwritten.</span></div></li>
              <li><span className="step-n">3</span><div><strong>Discover</strong><span>Keyword hits (security violation, linkage failed, halt…) become incident windows.</span></div></li>
              <li><span className="step-n">4</span><div><strong>Review</strong><span>Open the new incident for its timeline, root cause and actions.</span></div></li>
            </ol>
          </div>

          <div className="panel panel-pad">
            <h6 className="mb-2">Accepted files</h6>
            <ul className="plain-list">
              <li>LOGANALYZER text exports of SUMLOG: <span className="font-mono">{ACCEPTED.join(" ")}</span></li>
              <li>Day lines plus timestamped records, as produced by LOGANALYZER</li>
              <li>Up to {formatBytes(MAX_BYTES)} per file, several files at once</li>
            </ul>
          </div>

          <div className="panel">
            <div className="panel-head">
              <h6 className="m-0">Recent uploads</h6>
              <Link to="/audit" className="small text-decoration-none">Audit log</Link>
            </div>
            {uploads.loading ? (
              <Loading />
            ) : !uploads.data || uploads.data.length === 0 ? (
              <div className="empty py-4">No uploads yet.</div>
            ) : (
              uploads.data.map((u) => (
                <div key={u.batch_id} className="list-row">
                  <div className="text-truncate" style={{ fontSize: "0.88rem" }} title={u.filename}>{u.filename}</div>
                  <div className="small-label">
                    {u.records.toLocaleString()} records · {u.incidents.length} incident{u.incidents.length === 1 ? "" : "s"} ·{" "}
                    <span className="font-mono">{u.operator}</span> · {formatDateTime(u.created)}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
