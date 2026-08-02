import { apiClient } from "@/lib/api/client";
import type { AuthorizedVehicle, AuthorizedVehicleList, VehicleStatus, VehicleWrite } from "@/lib/api/types";

const statuses = new Set(["ACTIVE", "INACTIVE", "BLOCKED"]);
const object = (value: unknown): Record<string, unknown> => { if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("invalid object"); return value as Record<string, unknown>; };
const string = (value: unknown): string => { if (typeof value !== "string") throw new Error("invalid string"); return value; };
const nullableString = (value: unknown): string | null => value === null ? null : string(value);
const iso = (value: unknown): string => { const result = string(value); if (!Number.isFinite(Date.parse(result))) throw new Error("invalid date"); return result; };
const nullableIso = (value: unknown): string | null => value === null ? null : iso(value);

export function parseVehicle(value: unknown): AuthorizedVehicle {
  const item = object(value);
  const keys = ["id", "normalized_plate", "description", "status", "valid_from", "valid_until", "created_at", "updated_at"];
  if (Object.keys(item).length !== keys.length || keys.some((key) => !(key in item))) throw new Error("invalid fields");
  const status = string(item.status);
  if (!statuses.has(status) || !/^[A-Z0-9]+$/.test(string(item.normalized_plate))) throw new Error("invalid vehicle");
  return { id: string(item.id), normalized_plate: string(item.normalized_plate), description: nullableString(item.description), status: status as VehicleStatus, valid_from: nullableIso(item.valid_from), valid_until: nullableIso(item.valid_until), created_at: iso(item.created_at), updated_at: iso(item.updated_at) };
}

export function parseVehicles(value: unknown): AuthorizedVehicleList {
  const item = object(value);
  if (!Array.isArray(item.items) || !Number.isInteger(item.total_items) || (item.total_items as number) < 0 || Object.keys(item).length !== 2) throw new Error("invalid list");
  return { items: item.items.map(parseVehicle), total_items: item.total_items as number };
}

const json = (body: unknown): RequestInit => ({ headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
export const getVehicles = (query: Readonly<Record<string, string>>, signal?: AbortSignal) => apiClient.request("/api/authorized-vehicles", parseVehicles, { signal }, query);
export const createVehicle = (data: VehicleWrite) => apiClient.request("/api/authorized-vehicles", parseVehicle, { method: "POST", ...json(data) });
export const updateVehicle = (id: string, data: VehicleWrite) => apiClient.request(`/api/authorized-vehicles/${id}`, parseVehicle, { method: "PUT", ...json(data) });
export const setVehicleStatus = (id: string, status: VehicleStatus) => apiClient.request(`/api/authorized-vehicles/${id}/status`, parseVehicle, { method: "PATCH", ...json({ status }) });
