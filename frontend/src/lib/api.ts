import type { InputRelevance, AuthorityDetail, Candidate, LocationResult, Meta, ParsedFile, Report, ValidatedBoundary } from "./types";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new Error("SiteIQ's local service is not responding. Check that it is still running.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : `The request failed (${response.status}).`);
  }
  return response.json();
}
const post = <T,>(url: string, body: unknown, signal?: AbortSignal) => request<T>(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal });

export const api = {
  meta: () => request<Meta>("/api/meta"),
  authority: (key: string) => request<AuthorityDetail>(`/api/authorities/${encodeURIComponent(key)}`),
  identify: (body: Record<string, unknown>) => post<LocationResult>("/api/location/identify", body),
  parse: (file: File) => { const form = new FormData(); form.append("file", file); return request<ParsedFile>("/api/boundary/parse", { method: "POST", body: form }); },
  validate: (candidate: Candidate, scale: number | null, closeOpen: boolean) => post<ValidatedBoundary>("/api/boundary/validate", { candidate, scale_to_m: scale, close_open: closeOpen }),
  layers: () => request<{ authority: boolean; zone: boolean }>("/api/admin/layers"),
  installLayer: (layer: "authority" | "zone", file: File) => { const form = new FormData(); form.append("file", file); return request<{ feature_count: number; valid_polygon_count: number }>(`/api/admin/layers/${layer}`, { method: "POST", body: form }); },
  inputs: (body: Record<string, unknown>) => post<InputRelevance>("/api/inputs", body),
  assess: (payload: unknown, signal?: AbortSignal) => post<Report>("/api/assess", payload, signal),
  async download(kind: string, payload: unknown) {
    const response = await fetch(`/api/export/${kind}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!response.ok) { const body = await response.json().catch(() => null); throw new Error(body?.detail ?? "The export failed."); }
    const blob = await response.blob();
    const name = /filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") ?? "")?.[1] ?? "SiteIQ_export";
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = name; a.click();
    URL.revokeObjectURL(url);
  },
};
