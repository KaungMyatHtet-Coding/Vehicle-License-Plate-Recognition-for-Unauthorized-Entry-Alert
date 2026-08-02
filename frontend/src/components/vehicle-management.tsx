"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import { ApiRequestError } from "@/lib/api/client";
import { createVehicle, getVehicles, setVehicleStatus, updateVehicle } from "@/lib/api/vehicles";
import type { AuthorizedVehicle, VehicleStatus, VehicleWrite } from "@/lib/api/types";
import { ErrorState, LoadingState } from "@/components/feedback";
import { FoundationPanel } from "@/components/page-layout";

const button = "min-h-11 rounded-md bg-slate-900 px-4 py-2 font-semibold text-white disabled:opacity-50";
const input = "mt-2 block min-h-11 w-full rounded-md border px-3";

export function VehicleManagement() {
  const [items, setItems] = useState<ReadonlyArray<AuthorizedVehicle>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  const [formError, setFormError] = useState("");
  const [pending, setPending] = useState(false);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true); setError(false);
    try { setItems((await getVehicles(query, signal)).items); } catch { if (!signal?.aborted) setError(true); }
    finally { if (!signal?.aborted) setLoading(false); }
  }, [query]);
  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() => { if (!controller.signal.aborted) void load(controller.signal); });
    return () => controller.abort();
  }, [load]);

  const filter = (event: FormEvent) => { event.preventDefault(); const normalized = search.trim().toUpperCase().replace(/[^A-Z0-9]/g, ""); setQuery({ ...(normalized ? { search: normalized } : {}), ...(status ? { status_filter: status } : {}) }); };
  const create = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setFormError(""); setMessage("");
    const form = event.currentTarget;
    const data = new FormData(form);
    const plate = String(data.get("plate") ?? "").trim();
    if (!plate || !/[A-Za-z0-9]/.test(plate)) { setFormError("Enter a plate containing at least one letter or number."); return; }
    const payload: VehicleWrite = { plate_number: plate, description: String(data.get("description") ?? "").trim() || null, status: String(data.get("status")) as VehicleStatus, valid_from: data.get("valid_from") ? new Date(String(data.get("valid_from"))).toISOString() : null, valid_until: data.get("valid_until") ? new Date(String(data.get("valid_until"))).toISOString() : null };
    if (payload.valid_from && payload.valid_until && payload.valid_until <= payload.valid_from) { setFormError("Valid until must be later than valid from."); return; }
    setPending(true);
    try { await createVehicle(payload); form.reset(); setMessage("Authorized vehicle created."); await load(); }
    catch (err) { setFormError(err instanceof ApiRequestError && err.status === 409 ? "That normalized plate already exists." : "The vehicle could not be saved."); }
    finally { setPending(false); }
  };
  const changeStatus = async (vehicle: AuthorizedVehicle, next: VehicleStatus) => {
    if (!window.confirm(`Change ${vehicle.normalized_plate} to ${next}?`)) return;
    setMessage("");
    try { await setVehicleStatus(vehicle.id, next); setMessage(`${vehicle.normalized_plate} is now ${next}.`); await load(); }
    catch { setMessage("The status change could not be completed."); }
  };
  const edit = async (vehicle: AuthorizedVehicle) => {
    const plate = window.prompt("Plate number", vehicle.normalized_plate);
    if (plate === null) return;
    const description = window.prompt("Description (optional)", vehicle.description ?? "");
    if (description === null || !window.confirm(`Save changes to ${vehicle.normalized_plate}?`)) return;
    try {
      await updateVehicle(vehicle.id, { plate_number: plate, description: description.trim() || null, status: vehicle.status, valid_from: vehicle.valid_from, valid_until: vehicle.valid_until });
      setMessage(`${vehicle.normalized_plate} was updated.`); await load();
    } catch { setMessage("The vehicle update could not be completed."); }
  };

  return <div className="space-y-6">
    <FoundationPanel title="Add authorized vehicle" description="The backend normalizes plate numbers and remains authoritative for uniqueness, validity, status, and later entry decisions.">
      <form onSubmit={create} className="mt-5 grid gap-4 sm:grid-cols-2" aria-label="Add authorized vehicle">
        <label htmlFor="vehicle-plate" className="font-medium">Plate number<input id="vehicle-plate" name="plate" maxLength={32} required className={input} /></label>
        <label htmlFor="vehicle-create-status" className="font-medium">Status<select id="vehicle-create-status" name="status" className={input} defaultValue="ACTIVE"><option>ACTIVE</option><option>INACTIVE</option><option>BLOCKED</option></select></label>
        <label className="font-medium">Valid from (optional)<input name="valid_from" type="datetime-local" className={input} /></label>
        <label className="font-medium">Valid until (optional)<input name="valid_until" type="datetime-local" className={input} /></label>
        <label className="font-medium sm:col-span-2">Description (optional)<input name="description" maxLength={200} className={input} /></label>
        {formError ? <p role="alert" className="font-semibold text-red-700 sm:col-span-2">{formError}</p> : null}
        <button disabled={pending} className={`${button} sm:col-span-2`} type="submit">{pending ? "Saving…" : "Add vehicle"}</button>
      </form>
    </FoundationPanel>
    <form onSubmit={filter} className="grid gap-4 rounded-xl border bg-white p-5 sm:grid-cols-[1fr_1fr_auto]" aria-label="Vehicle filters">
      <label htmlFor="vehicle-search" className="font-medium">Search plate<input id="vehicle-search" value={search} onChange={(e) => setSearch(e.target.value)} className={input} /></label>
      <label htmlFor="vehicle-filter-status" className="font-medium">Status<select id="vehicle-filter-status" value={status} onChange={(e) => setStatus(e.target.value)} className={input}><option value="">All statuses</option><option>ACTIVE</option><option>INACTIVE</option><option>BLOCKED</option></select></label>
      <button className={`${button} self-end`}>Apply filters</button>
    </form>
    {message ? <p role="status" className="rounded-md bg-teal-50 p-3 font-semibold text-teal-900">{message}</p> : null}
    {loading ? <LoadingState label="Loading authorized vehicles" /> : error ? <ErrorState message="Authorized vehicles could not be loaded." retry={() => void load()} /> : items.length === 0 ? <FoundationPanel title="No matching vehicles" description="No process-local authorized vehicle records match these filters." /> : <div className="overflow-x-auto rounded-xl border bg-white"><table className="w-full min-w-[800px] text-left"><thead><tr className="border-b bg-slate-50"><th className="p-3">Plate</th><th className="p-3">Status</th><th className="p-3">Validity</th><th className="p-3">Description</th><th className="p-3">Actions</th></tr></thead><tbody>{items.map((vehicle) => <tr className="border-b" key={vehicle.id}><td className="p-3 font-semibold">{vehicle.normalized_plate}</td><td className="p-3">{vehicle.status}</td><td className="p-3">{vehicle.valid_from ?? "No start"} – {vehicle.valid_until ?? "No end"}</td><td className="p-3">{vehicle.description ?? "—"}</td><td className="p-3"><div className="flex gap-2"><button type="button" className="font-semibold text-teal-800 underline" onClick={() => void edit(vehicle)}>Edit</button><select aria-label={`Change status for ${vehicle.normalized_plate}`} value={vehicle.status} onChange={(e) => void changeStatus(vehicle, e.target.value as VehicleStatus)} className="min-h-11 rounded-md border px-2"><option>ACTIVE</option><option>INACTIVE</option><option>BLOCKED</option></select></div></td></tr>)}</tbody></table></div>}
  </div>;
}
