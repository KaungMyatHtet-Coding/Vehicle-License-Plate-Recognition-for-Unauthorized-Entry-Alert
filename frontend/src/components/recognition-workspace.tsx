"use client";

import { useEffect, useRef, useState } from "react";

import { ApiRequestError } from "@/lib/api/client";
import { analyzeVehicleImage } from "@/lib/api/recognition";
import type { RecognitionResponse } from "@/lib/api/types";

type Analyze = (file: File, signal?: AbortSignal) => Promise<RecognitionResponse>;
type ViewState =
  | { kind: "idle" }
  | { kind: "ready" }
  | { kind: "running" }
  | { kind: "result"; result: RecognitionResponse }
  | { kind: "error"; title: string; message: string; correlationId: string | null };

const ACCEPTED_TYPES = new Set(["image/jpeg", "image/png"]);

function errorView(error: unknown): Extract<ViewState, { kind: "error" }> {
  if (error instanceof ApiRequestError) {
    if (error.code === "API_REQUEST_TIMEOUT") {
      return {
        kind: "error",
        title: "Recognition timed out",
        message: "The server took too long to respond. Please try again.",
        correlationId: null,
      };
    }
    if (error.code === "API_UNAVAILABLE") {
      return {
        kind: "error",
        title: "Network unavailable",
        message: "The recognition service could not be reached. Check your connection and try again.",
        correlationId: null,
      };
    }
    return {
      kind: "error",
      title: error.status && error.status < 500 ? "Image not accepted" : "Recognition unavailable",
      message: error.message,
      correlationId: error.correlationId,
    };
  }
  return {
    kind: "error",
    title: "Recognition unavailable",
    message: "The request could not be completed. No entry decision was made.",
    correlationId: null,
  };
}

function decisionStyle(decision: string): string {
  if (decision === "AUTHORIZED") return "border-emerald-300 bg-emerald-50 text-emerald-950";
  if (decision === "UNAUTHORIZED") return "border-red-300 bg-red-50 text-red-950";
  return "border-amber-300 bg-amber-50 text-amber-950";
}

export function RecognitionWorkspace({
  analyze = analyzeVehicleImage,
}: Readonly<{ analyze?: Analyze }>) {
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [state, setState] = useState<ViewState>({ kind: "idle" });
  const abortRef = useRef<AbortController | null>(null);
  const submittingRef = useRef(false);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  function clearPreview() {
    setPreviewUrl(null);
  }

  function selectFile(selected: File | null) {
    if (!selected) return;
    clearPreview();
    setFile(selected);
    if (!ACCEPTED_TYPES.has(selected.type)) {
      setState({
        kind: "error",
        title: "Image not accepted",
        message: "Choose a JPEG or PNG image.",
        correlationId: null,
      });
      return;
    }
    setPreviewUrl(URL.createObjectURL(selected));
    setState({ kind: "ready" });
  }

  function reset() {
    abortRef.current?.abort();
    abortRef.current = null;
    submittingRef.current = false;
    clearPreview();
    setFile(null);
    setState({ kind: "idle" });
  }

  async function submit() {
    if (!file || state.kind === "running" || submittingRef.current) return;
    submittingRef.current = true;
    const controller = new AbortController();
    abortRef.current = controller;
    setState({ kind: "running" });
    try {
      const result = await analyze(file, controller.signal);
      setState({ kind: "result", result });
    } catch (error) {
      if (!controller.signal.aborted) setState(errorView(error));
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      submittingRef.current = false;
    }
  }

  const disabled = state.kind === "running";
  const result = state.kind === "result" ? state.result : null;
  const loggingResult = result?.logging ?? null;
  const decision = loggingResult?.decision ?? null;

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1.05fr)_minmax(20rem,0.95fr)]">
      <section className="rounded-xl border border-[var(--border)] bg-white p-5 shadow-sm sm:p-6">
        <h2 className="text-lg font-semibold text-slate-950">Vehicle image</h2>
        <p className="mt-2 leading-6 text-slate-600">
          Choose one JPEG or PNG image with a clearly visible plate. The image is sent only when you select Analyze image.
        </p>
        <label className="mt-5 block font-semibold text-slate-900" htmlFor="vehicle-image">
          Select vehicle image
        </label>
        <input
          id="vehicle-image"
          type="file"
          accept="image/jpeg,image/png,.jpg,.jpeg,.png"
          disabled={disabled}
          onChange={(event) => selectFile(event.target.files?.[0] ?? null)}
          className="mt-2 block w-full rounded-lg border border-slate-300 bg-slate-50 p-3 text-sm file:mr-4 file:rounded-md file:border-0 file:bg-[var(--brand)] file:px-4 file:py-2 file:font-semibold file:text-white disabled:cursor-not-allowed disabled:opacity-60"
        />
        {previewUrl && file ? (
          <div className="mt-5">
            {/* Local blob previews cannot use the Next image optimizer. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={previewUrl}
              alt={`Preview of ${file.name}`}
              className="max-h-[28rem] w-full rounded-lg border border-slate-200 bg-slate-100 object-contain"
            />
            <p className="mt-2 break-all text-sm text-slate-600">
              {file.name} · {(file.size / 1024).toFixed(1)} KB
            </p>
          </div>
        ) : null}
        <div className="mt-5 flex flex-wrap gap-3">
          <button
            type="button"
            onClick={submit}
            disabled={!file || disabled || !ACCEPTED_TYPES.has(file.type)}
            className="min-h-11 rounded-md bg-[var(--brand)] px-5 py-2 font-semibold text-white transition-colors hover:bg-[var(--brand-strong)] focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-600 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:bg-slate-400"
          >
            {disabled ? "Analyzing…" : "Analyze image"}
          </button>
          {file ? (
            <button
              type="button"
              onClick={reset}
              disabled={disabled}
              className="min-h-11 rounded-md border border-slate-300 bg-white px-5 py-2 font-semibold text-slate-800 transition-colors hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-600 focus-visible:ring-offset-2 disabled:opacity-60"
            >
              {result ? "Analyze another image" : "Remove image"}
            </button>
          ) : null}
        </div>
      </section>

      <section aria-labelledby="recognition-result" className="min-w-0">
        <h2 id="recognition-result" className="sr-only">Recognition result</h2>
        {state.kind === "idle" || state.kind === "ready" ? (
          <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-6 text-slate-700">
            <p className="font-semibold">{state.kind === "ready" ? "Ready to analyze" : "No image selected"}</p>
            <p className="mt-2 leading-6">
              {state.kind === "ready" ? "Review the preview, then submit it for an authoritative backend decision." : "Select a supported vehicle image to begin."}
            </p>
          </div>
        ) : null}
        {state.kind === "running" ? (
          <div role="status" aria-live="polite" className="rounded-xl border border-teal-200 bg-teal-50 p-6">
            <div aria-hidden="true" className="h-2 w-28 animate-pulse rounded-full bg-teal-700" />
            <p className="mt-4 font-semibold text-teal-950">Analyzing vehicle image…</p>
            <p className="mt-2 text-teal-800">Detecting the plate, reading its text, checking authorization, and recording the outcome.</p>
          </div>
        ) : null}
        {state.kind === "error" ? (
          <div role="alert" className="rounded-xl border border-red-300 bg-red-50 p-6 text-red-950">
            <h3 className="text-lg font-semibold">{state.title}</h3>
            <p className="mt-2 leading-6">{state.message}</p>
            {state.correlationId ? <p className="mt-3 text-sm">Reference: {state.correlationId}</p> : null}
          </div>
        ) : null}
        {result?.status === "no_plate_detected" ? (
          <div role="status" className="rounded-xl border border-amber-300 bg-amber-50 p-6 text-amber-950">
            <p className="text-xs font-bold uppercase tracking-wider">No plate detected</p>
            <h3 className="mt-2 text-xl font-semibold">Manual inspection needed</h3>
            <p className="mt-2 leading-6">{result.message}</p>
            <p className="mt-4 text-sm">Reference: {result.correlation_id}</p>
          </div>
        ) : null}
        {result?.status === "completed" && decision ? (
          <div role="status" className={`rounded-xl border p-6 ${decisionStyle(decision.decision)}`}>
            <p className="text-xs font-bold uppercase tracking-wider">Authoritative result</p>
            <h3 className="mt-2 text-2xl font-bold">{decision.decision.replace("_", " ")}</h3>
            <p className="mt-2 leading-6">{decision.message}</p>
            <dl className="mt-5 grid gap-4 sm:grid-cols-2">
              <div><dt className="text-sm font-semibold">Normalized plate</dt><dd className="mt-1 text-lg">{decision.normalized_plate || "Not available"}</dd></div>
              <div><dt className="text-sm font-semibold">Confidence</dt><dd className="mt-1 text-lg">{decision.confidence === null ? "Not available" : `${(decision.confidence * 100).toFixed(1)}%`}</dd></div>
              <div><dt className="text-sm font-semibold">Raw OCR text</dt><dd className="mt-1">{result.ocr?.raw_text || "Not available"}</dd></div>
              <div><dt className="text-sm font-semibold">Reason code</dt><dd className="mt-1 break-words">{decision.reason}</dd></div>
            </dl>
            {result.selected_plate ? (
              <div className="mt-5 border-t border-current/20 pt-5">
                <p className="text-sm font-semibold">Detected plate crop</p>
                {/* The crop is a validated in-memory data URL from the API. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={`data:${result.selected_plate.crop.media_type};base64,${result.selected_plate.crop.base64_data}`}
                  alt="Detected license plate crop"
                  className="mt-2 max-h-36 rounded-md border border-current/20 bg-white object-contain"
                />
              </div>
            ) : null}
            <div className="mt-5 border-t border-current/20 pt-4 text-sm">
              <p>
                Processing: {result.timings.total_ms.toFixed(1)} ms · {result.detection_count} plate candidate{result.detection_count === 1 ? "" : "s"}
              </p>
              <p className="mt-1">
                Evidence: {loggingResult?.evidence_available ? "stored privately" : "not available"} · Log: {loggingResult?.log_persisted ? "recorded" : "not recorded"}
              </p>
              {loggingResult?.status === "partial_failure" ? (
                <p className="mt-2 font-semibold">The decision is unchanged, but some evidence or logging work could not be completed.</p>
              ) : null}
              <p className="mt-2 break-all">Reference: {result.correlation_id}</p>
            </div>
          </div>
        ) : null}
      </section>
    </div>
  );
}
