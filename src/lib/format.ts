import { useCallback, useEffect, useRef, useState } from "react";

// Backend timestamps have no time zone: event times are MCP local time as written in the SUMLOG.
// Format them from the string itself so the browser never shifts them.
export const TIMEZONE_LABEL = "MCP local time";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export const formatTime = (iso: string | null | undefined) => (iso ? iso.slice(11, 16) : "—");
export const formatTimeSec = (iso: string | null | undefined) => (iso ? iso.slice(11, 19) : "—");

export const formatDate = (iso: string | null | undefined) => {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${Number(d)} ${MONTHS[Number(m) - 1] ?? m} ${y}`;
};

export const formatDateTime = (iso: string | null | undefined) => (iso ? `${formatDate(iso)} ${formatTime(iso)}` : "—");

const ms = (iso: string) => new Date(iso).getTime();

export const secondsBetween = (startIso: string, endIso: string) => Math.max(0, Math.round((ms(endIso) - ms(startIso)) / 1000));

export const formatDuration = (seconds: number) => {
  if (seconds < 60) return `${Math.round(seconds)} s`;
  const min = Math.round(seconds / 60);
  if (min < 60) return `${min} min`;
  return `${Math.floor(min / 60)} h ${min % 60} min`;
};

// "10 Aug 2023 11:11–11:41" (or across days: "10 Aug 2023 23:50 – 11 Aug 2023 00:20")
export const formatSpan = (startIso: string, endIso: string) =>
  startIso.slice(0, 10) === endIso.slice(0, 10)
    ? `${formatDate(startIso)} ${formatTime(startIso)}–${formatTime(endIso)}`
    : `${formatDateTime(startIso)} – ${formatDateTime(endIso)}`;

export const formatBytes = (n: number) =>
  n < 1024 ? `${n} B` : n < 1024 ** 2 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1024 ** 2).toFixed(1)} MB`;

export function useElapsed(running: boolean) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!running) return;
    setSeconds(0);
    const id = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [running]);
  return seconds;
}

// Load data from an async function; `enabled: false` defers the call until reload() is used.
export function useApi<T>(fn: () => Promise<T>, deps: unknown[], opts: { enabled?: boolean } = {}) {
  const enabled = opts.enabled ?? true;
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(enabled);
  const seq = useRef(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const reload = useCallback(async () => {
    const mine = ++seq.current;
    setLoading(true);
    setError(null);
    try {
      const value = await fnRef.current();
      if (mine === seq.current) setData(value);
      return value;
    } catch (e) {
      if (mine === seq.current) setError(e as Error);
      return null;
    } finally {
      if (mine === seq.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (enabled) void reload();
    else setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ...deps]);

  return { data, error, loading, reload, setData };
}
