import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ActionRow, AuditEntry, CatalogEntry, Decision, Health, IncidentRow, Prediction, Summary } from "../types";
import { api } from "../api";
import { CURRENT_OPERATOR } from "../lib/labels";

// App-wide data from the backend. Per-incident data (timeline, RCA, actions, correlation) is loaded by the
// incident pages themselves. Every mutation calls the API and then refreshes this shared data.

interface AppData {
  summary: Summary | null;
  incidents: IncidentRow[];
  predictions: Prediction[];
  activePredictions: Prediction[];
  pendingApprovals: ActionRow[];
  audit: AuditEntry[];
  health: Health | null;
  catalog: Record<string, CatalogEntry>;
  loading: boolean;
  error: Error | null;
  backendOnline: boolean;
  ingesting: boolean;
  refresh: (opts?: { predictions?: boolean }) => Promise<void>;
  predictionsLoading: boolean;
  runIngest: () => Promise<void>;
  decide: (incidentId: string, actionId: string, decision: Decision, note?: string) => Promise<ActionRow>;
  dismissPrediction: (alertId: string, reason: string) => Promise<void>;
  openPrediction: (alertId: string) => Promise<string>;
}

const Ctx = createContext<AppData | undefined>(undefined);

export const IncidentProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [incidents, setIncidents] = useState<IncidentRow[]>([]);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [pendingApprovals, setPendingApprovals] = useState<ActionRow[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [catalog, setCatalog] = useState<Record<string, CatalogEntry>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [backendOnline, setBackendOnline] = useState(true);
  const [ingesting, setIngesting] = useState(false);
  const [predictionsLoading, setPredictionsLoading] = useState(true);

  const loadHealth = useCallback(async () => {
    try {
      setHealth(await api.health());
      setBackendOnline(true);
    } catch {
      setBackendOnline(false);
    }
  }, []);

  // The prediction scan is slow on the backend (~10 s), so it loads on its own and only when it can have changed.
  const loadPredictions = useCallback(async () => {
    setPredictionsLoading(true);
    try {
      setPredictions(await api.predictions());
    } catch {
      // keep the previous list; the core error state covers an offline backend
    } finally {
      setPredictionsLoading(false);
    }
  }, []);

  const refresh = useCallback(
    async (opts: { predictions?: boolean } = {}) => {
      void loadHealth();
      if (opts.predictions ?? true) void loadPredictions();
      const track = <T,>(p: Promise<T>, set: (v: T) => void) => p.then(set);
      const results = await Promise.allSettled([
        track(api.summary(), setSummary),
        track(api.incidents(), setIncidents),
        track(api.actions("pending", "needs_approval"), setPendingApprovals),
        track(api.audit(500), setAudit),
        track(api.catalog(), (c) => setCatalog(Object.fromEntries(c.map((e) => [e.id, e])))),
      ]);
      const failed = results.find((r) => r.status === "rejected") as PromiseRejectedResult | undefined;
      setError(failed ? (failed.reason as Error) : null);
      setLoading(false);
    },
    [loadHealth, loadPredictions]
  );

  useEffect(() => {
    void refresh();
    const healthTimer = setInterval(loadHealth, 30_000);
    const onFocus = () => void refresh({ predictions: false });
    window.addEventListener("focus", onFocus);
    return () => {
      clearInterval(healthTimer);
      window.removeEventListener("focus", onFocus);
    };
  }, [refresh, loadHealth]);

  const runIngest = useCallback(async () => {
    setIngesting(true);
    try {
      await api.ingest();
    } finally {
      setIngesting(false);
      await refresh();
    }
  }, [refresh]);

  const decide = useCallback(
    async (incidentId: string, actionId: string, decision: Decision, note?: string) => {
      const row = await api.decide(incidentId, actionId, decision, CURRENT_OPERATOR.id, note);
      await refresh({ predictions: false });
      return row;
    },
    [refresh]
  );

  const dismissPrediction = useCallback(
    async (alertId: string, reason: string) => {
      await api.dismissPrediction(alertId, CURRENT_OPERATOR.id, reason);
      await refresh();
    },
    [refresh]
  );

  const openPrediction = useCallback(
    async (alertId: string) => {
      const res = await api.openPrediction(alertId, CURRENT_OPERATOR.id);
      await refresh();
      return res.incident_id as string;
    },
    [refresh]
  );

  const activePredictions = useMemo(() => predictions.filter((p) => p.status === "active"), [predictions]);

  return (
    <Ctx.Provider
      value={{
        summary,
        incidents,
        predictions,
        activePredictions,
        pendingApprovals,
        audit,
        health,
        catalog,
        loading,
        error,
        backendOnline,
        ingesting,
        refresh,
        predictionsLoading,
        runIngest,
        decide,
        dismissPrediction,
        openPrediction,
      }}
    >
      {children}
    </Ctx.Provider>
  );
};

export const useIncidents = (): AppData => {
  const context = useContext(Ctx);
  if (!context) throw new Error("useIncidents must be used within an IncidentProvider");
  return context;
};
