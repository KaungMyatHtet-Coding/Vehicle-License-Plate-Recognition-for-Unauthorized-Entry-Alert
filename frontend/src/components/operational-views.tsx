"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { ErrorState, LoadingState } from "@/components/feedback";
import { FoundationPanel } from "@/components/page-layout";
import { getAlerts, getDetection, getHistory, getStatistics } from "@/lib/api/operations";
import { ApiRequestError } from "@/lib/api/client";
import type { DashboardStatistics, DetectionDetail, PaginatedAlerts, PaginatedDetections } from "@/lib/api/types";

const utc = (value: string) => `${new Intl.DateTimeFormat("en-GB", { year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", timeZone: "UTC" }).format(new Date(value))} UTC`;
const button =
  "min-h-11 rounded-md bg-slate-900 px-4 py-2 font-semibold text-white transition-colors hover:bg-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-600 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50";

function useLoad<T>(loader: (signal: AbortSignal) => Promise<T>, dependencies: readonly unknown[]) {
  const [state, setState] = useState<{ data: T | null; error: boolean; loading: boolean }>({ data: null, error: false, loading: true });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() => {
      if (!controller.signal.aborted) {
        setState({ data: null, error: false, loading: true });
      }
    });
    loader(controller.signal).then((data) => setState({ data, error: false, loading: false })).catch(() => {
      if (!controller.signal.aborted) setState({ data: null, error: true, loading: false });
    });
    return () => controller.abort();
    // The caller supplies primitive query dependencies intentionally.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...dependencies, attempt]);
  return { ...state, retry: () => setAttempt((value) => value + 1) };
}

export function DashboardView() {
  const loader = useCallback((signal: AbortSignal) => getStatistics(signal), []);
  const state = useLoad<DashboardStatistics>(loader, []);
  if (state.loading) return <LoadingState label="Loading server-derived statistics" />;
  if (state.error || !state.data) return <ErrorState message="Dashboard statistics could not be loaded." retry={state.retry} />;
  const data = state.data;
  return <div className="space-y-6">
    <p className="text-sm text-slate-600">All totals and daily trend boundaries are calculated by the backend in {data.timezone}.</p>
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
      {[["Total", data.total_recognitions], ["Authorized", data.authorized], ["Unauthorized", data.unauthorized], ["Manual review", data.manual_review], ["No plate", data.no_plate]].map(([label, value]) =>
        <FoundationPanel key={label} title={String(label)} description={String(value)} />)}
    </div>
    {data.total_recognitions === 0 ? <FoundationPanel title="No recognition activity" description="Process-local history is empty. Activity may be cleared when the backend restarts." /> :
      <FoundationPanel title="Seven-day recognition trend" description="Daily authoritative outcomes; bars represent total activity.">
        <ul className="mt-5 space-y-3">{data.trend.map((item) => <li key={item.bucket_start} className="grid grid-cols-[7rem_1fr_3rem] items-center gap-3"><span>{utc(item.bucket_start).split(",")[0]}</span><span className="h-3 rounded bg-teal-600" style={{ width: `${Math.max(4, Math.min(100, item.total * 10))}%` }} aria-label={`${item.total} recognitions`} /><strong>{item.total}</strong></li>)}</ul>
      </FoundationPanel>}
  </div>;
}

export function HistoryView() {
  const [page, setPage] = useState(1);
  const [decision, setDecision] = useState("");
  const [plate, setPlate] = useState("");
  const [query, setQuery] = useState<Record<string, string>>({ page: "1", page_size: "10" });
  const [filterError, setFilterError] = useState("");
  const [detailState, setDetailState] = useState<
    | { status: "idle" | "loading" | "not_found" | "error" | "invalid" | "timeout"; data: null }
    | { status: "success"; data: DetectionDetail }
  >({ status: "idle", data: null });
  const detailRequest = useRef(0);
  const loader = useCallback((signal: AbortSignal) => getHistory(query, signal), [query]);
  const state = useLoad<PaginatedDetections>(loader, [query]);
  const clearDetail = () => {
    detailRequest.current += 1;
    setDetailState({ status: "idle", data: null });
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const normalized = plate.trim().toUpperCase();
    if (normalized && !/^[A-Z0-9]+$/.test(normalized)) {
      setFilterError("Use only letters A–Z and numbers 0–9 for the normalized plate.");
      return;
    }
    setFilterError("");
    setPage(1);
    clearDetail();
    setQuery({ page: "1", page_size: "10", ...(decision ? { decision } : {}), ...(normalized ? { normalized_plate: normalized } : {}) });
  };
  const move = (next: number) => { setPage(next); setQuery((current) => ({ ...current, page: String(next) })); clearDetail(); };
  const openDetail = async (correlationId: string) => {
    const request = detailRequest.current + 1;
    detailRequest.current = request;
    setDetailState({ status: "loading", data: null });
    try {
      const data = await getDetection(correlationId);
      if (detailRequest.current === request) setDetailState({ status: "success", data });
    } catch (error) {
      if (detailRequest.current !== request) return;
      if (error instanceof ApiRequestError && error.status === 404) {
        setDetailState({ status: "not_found", data: null });
      } else if (error instanceof ApiRequestError && error.code === "API_RESPONSE_INVALID") {
        setDetailState({ status: "invalid", data: null });
      } else if (error instanceof ApiRequestError && error.code === "API_REQUEST_TIMEOUT") {
        setDetailState({ status: "timeout", data: null });
      } else {
        setDetailState({ status: "error", data: null });
      }
    }
  };
  return <div className="space-y-6">
    <form onSubmit={submit} className="grid gap-4 rounded-xl border bg-white p-5 sm:grid-cols-[1fr_1fr_auto]" aria-label="History filters">
      <label className="font-medium">Decision<select value={decision} onChange={(e) => setDecision(e.target.value)} className="mt-2 block min-h-11 w-full rounded-md border px-3"><option value="">All decisions</option><option>AUTHORIZED</option><option>UNAUTHORIZED</option><option>MANUAL_REVIEW</option></select></label>
      <label className="font-medium">Normalized plate<input value={plate} onChange={(e) => { const value = e.target.value; setPlate(value); if (!value.trim() || /^[A-Za-z0-9]+$/.test(value.trim())) setFilterError(""); }} onInvalid={() => setFilterError("Use only letters A–Z and numbers 0–9 for the normalized plate.")} pattern="[A-Za-z0-9]*" aria-describedby={filterError ? "plate-filter-error" : undefined} aria-invalid={filterError ? "true" : undefined} className="mt-2 block min-h-11 w-full rounded-md border px-3" />{filterError ? <span id="plate-filter-error" role="alert" aria-live="assertive" className="mt-2 block text-sm font-semibold text-red-700">{filterError}</span> : null}</label>
      <button className={`${button} self-end`} type="submit">Apply filters</button>
    </form>
    {state.loading ? <LoadingState label="Loading detection history" /> : state.error || !state.data ? <ErrorState message="Detection history could not be loaded." retry={state.retry} /> : state.data.items.length === 0 ? <FoundationPanel title="No matching detections" description="No process-local records match these filters." /> : <>
      <div className="overflow-x-auto rounded-xl border bg-white"><table className="w-full min-w-[700px] text-left"><thead><tr className="border-b bg-slate-50"><th className="p-3">Time (UTC)</th><th className="p-3">Decision</th><th className="p-3">Plate</th><th className="p-3">Reason</th><th className="p-3">Detail</th></tr></thead><tbody>{state.data.items.map((item) => <tr key={item.correlation_id} className="border-b"><td className="p-3">{utc(item.created_at)}</td><td className="p-3 font-semibold">{item.decision}</td><td className="p-3">{item.normalized_plate || "Not available"}</td><td className="p-3">{item.reason_message}</td><td className="p-3"><button type="button" className="font-semibold text-teal-800 underline" onClick={() => void openDetail(item.correlation_id)}>View</button></td></tr>)}</tbody></table></div>
      <div className="flex items-center justify-between"><button className={button} disabled={page <= 1} onClick={() => move(page - 1)}>Previous</button><span>Page {page} of {state.data.total_pages}</span><button className={button} disabled={page >= state.data.total_pages} onClick={() => move(page + 1)}>Next</button></div>
    </>}
    {detailState.status === "loading" ? <LoadingState label="Loading event detail" /> : null}
    {detailState.status === "not_found" ? <ErrorState title="Detection not found" message="This detection record is no longer available." /> : null}
    {detailState.status === "invalid" ? <ErrorState title="Detection detail unavailable" message="The detection details could not be verified safely." /> : null}
    {detailState.status === "timeout" ? <ErrorState title="Detection detail timed out" message="The detection detail request timed out. Try opening it again." /> : null}
    {detailState.status === "error" ? <ErrorState title="Detection detail unavailable" message="The detection details could not be loaded. The history list is unchanged." /> : null}
    {detailState.status === "success" ? <FoundationPanel title="Event detail" description={`${detailState.data.decision}: ${detailState.data.reason_message}`}><dl className="mt-4 grid gap-2"><div><dt className="font-semibold">Recorded</dt><dd>{utc(detailState.data.created_at)}</dd></div><div><dt className="font-semibold">Evidence</dt><dd>{detailState.data.evidence_available ? "Available, but access is restricted" : "Not available"}</dd></div></dl></FoundationPanel> : null}
  </div>;
}

export function AlertsView() {
  const [page, setPage] = useState(1);
  const loader = useCallback((signal: AbortSignal) => getAlerts(page, signal), [page]);
  const state = useLoad<PaginatedAlerts>(loader, [page]);
  if (state.loading) return <LoadingState label="Loading backend-selected alerts" />;
  if (state.error || !state.data) return <ErrorState message="Alerts could not be loaded." retry={state.retry} />;
  return <div className="space-y-5">{state.data.items.length === 0 ? <FoundationPanel title="No operational alerts" description="The backend selected no unauthorized or manual-review records for review." /> : state.data.items.map((item) => <article key={item.correlation_id} className={`rounded-xl border p-5 ${item.decision === "MANUAL_REVIEW" ? "border-violet-300 bg-violet-50" : "border-amber-300 bg-amber-50"}`}><p className="text-sm font-bold uppercase tracking-wide">{item.decision === "MANUAL_REVIEW" ? "Manual review" : "Entry not authorized"}</p><h2 className="mt-2 text-lg font-semibold">{item.normalized_plate || "Plate unavailable"}</h2><p className="mt-2">{item.reason_message}</p><p className="mt-2 text-sm">{utc(item.created_at)} · Selected by the backend</p></article>)}{state.data.total_pages > 1 ? <div className="flex justify-between"><button className={button} disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button><button className={button} disabled={page >= state.data.total_pages} onClick={() => setPage(page + 1)}>Next</button></div> : null}</div>;
}
