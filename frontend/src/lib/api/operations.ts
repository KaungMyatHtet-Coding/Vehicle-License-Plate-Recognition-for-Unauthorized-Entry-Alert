import { apiClient } from "@/lib/api/client";
import type {
  AlertSummary,
  DashboardStatistics,
  DecisionReason,
  DecisionStatus,
  DetectionDetail,
  DetectionSummary,
  PaginatedAlerts,
  PaginatedDetections,
  TrendBucket,
} from "@/lib/api/types";

const DECISIONS = new Set(["AUTHORIZED", "UNAUTHORIZED", "MANUAL_REVIEW"]);
const REASONS = new Set([
  "ACTIVE_MATCH", "OCR_EMPTY", "OCR_LOW_CONFIDENCE", "OCR_RESULT_INVALID",
  "DECISION_TIME_INVALID", "VEHICLE_NOT_FOUND", "VEHICLE_INACTIVE",
  "VEHICLE_BLOCKED", "VEHICLE_NOT_YET_VALID", "VEHICLE_EXPIRED",
  "VEHICLE_RECORD_INVALID", "VEHICLE_LOOKUP_FAILED",
]);

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("invalid object");
  return value as Record<string, unknown>;
}
function string(value: unknown): string { if (typeof value !== "string") throw new Error("invalid string"); return value; }
function integer(value: unknown): number { if (!Number.isInteger(value) || (value as number) < 0) throw new Error("invalid integer"); return value as number; }
function number(value: unknown): number { if (typeof value !== "number" || !Number.isFinite(value)) throw new Error("invalid number"); return value; }
function boolean(value: unknown): boolean { if (typeof value !== "boolean") throw new Error("invalid boolean"); return value; }
function exact(item: Record<string, unknown>, keys: readonly string[]) {
  if (Object.keys(item).length !== keys.length || keys.some((key) => !(key in item))) throw new Error("invalid fields");
}
function iso(value: unknown): string { const result = string(value); if (!Number.isFinite(Date.parse(result))) throw new Error("invalid date"); return result; }

function summary(value: unknown): DetectionSummary {
  const item = object(value);
  exact(item, ["correlation_id", "decision", "reason", "reason_message", "normalized_plate", "confidence", "created_at", "evidence_available"]);
  const decision = string(item.decision);
  const reason = string(item.reason);
  if (!DECISIONS.has(decision) || !REASONS.has(reason)) throw new Error("invalid decision");
  const confidence = item.confidence === null ? null : number(item.confidence);
  if (confidence !== null && (confidence < 0 || confidence > 1)) throw new Error("invalid confidence");
  return {
    correlation_id: string(item.correlation_id), decision: decision as DecisionStatus,
    reason: reason as DecisionReason, reason_message: string(item.reason_message),
    normalized_plate: string(item.normalized_plate), confidence,
    created_at: iso(item.created_at), evidence_available: boolean(item.evidence_available),
  };
}

export function parseHistory(value: unknown): PaginatedDetections {
  const item = object(value);
  exact(item, ["items", "page", "page_size", "total_items", "total_pages", "timezone"]);
  if (!Array.isArray(item.items) || item.timezone !== "UTC") throw new Error("invalid history");
  return { items: item.items.map(summary), page: integer(item.page), page_size: integer(item.page_size), total_items: integer(item.total_items), total_pages: integer(item.total_pages), timezone: "UTC" };
}

export function parseDetail(value: unknown): DetectionDetail {
  const item = object(value);
  const base = summary(Object.fromEntries(Object.entries(item).filter(([key]) => !["timings", "evidence_access"].includes(key))));
  if (item.evidence_access !== "restricted") throw new Error("invalid evidence access");
  const timings = object(item.timings);
  for (const value of Object.values(timings)) number(value);
  return { ...base, timings: timings as Record<string, number>, evidence_access: "restricted" };
}

function trend(value: unknown): TrendBucket {
  const item = object(value);
  exact(item, ["bucket_start", "authorized", "unauthorized", "manual_review", "no_plate", "total"]);
  return { bucket_start: iso(item.bucket_start), authorized: integer(item.authorized), unauthorized: integer(item.unauthorized), manual_review: integer(item.manual_review), no_plate: integer(item.no_plate), total: integer(item.total) };
}

export function parseStatistics(value: unknown): DashboardStatistics {
  const item = object(value);
  exact(item, ["total_recognitions", "authorized", "unauthorized", "manual_review", "no_plate", "timezone", "trend_granularity", "trend"]);
  if (item.timezone !== "UTC" || item.trend_granularity !== "day" || !Array.isArray(item.trend)) throw new Error("invalid statistics");
  return { total_recognitions: integer(item.total_recognitions), authorized: integer(item.authorized), unauthorized: integer(item.unauthorized), manual_review: integer(item.manual_review), no_plate: integer(item.no_plate), timezone: "UTC", trend_granularity: "day", trend: item.trend.map(trend) };
}

export function parseAlerts(value: unknown): PaginatedAlerts {
  const item = object(value);
  exact(item, ["items", "page", "page_size", "total_items", "total_pages", "timezone"]);
  if (!Array.isArray(item.items) || item.timezone !== "UTC") throw new Error("invalid alerts");
  const items = item.items.map((value): AlertSummary => {
    const alert = object(value);
    const base = summary(Object.fromEntries(Object.entries(alert).filter(([key]) => !["alert_type", "message"].includes(key))));
    if (alert.alert_type !== "ENTRY_NOT_AUTHORIZED" || base.decision !== "UNAUTHORIZED") throw new Error("invalid alert");
    return { ...base, alert_type: "ENTRY_NOT_AUTHORIZED", message: string(alert.message) };
  });
  return { items, page: integer(item.page), page_size: integer(item.page_size), total_items: integer(item.total_items), total_pages: integer(item.total_pages), timezone: "UTC" };
}

export const getStatistics = (signal?: AbortSignal) => apiClient.request("/api/dashboard/statistics", parseStatistics, { signal });
export const getHistory = (query: Readonly<Record<string, string>>, signal?: AbortSignal) => apiClient.request("/api/detections", parseHistory, { signal }, query);
export const getDetection = (id: string, signal?: AbortSignal) => apiClient.request(`/api/detections/${id}`, parseDetail, { signal });
export const getAlerts = (page: number, signal?: AbortSignal) => apiClient.request("/api/alerts", parseAlerts, { signal }, { page: String(page), page_size: "10" });
