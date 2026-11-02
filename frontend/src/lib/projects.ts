import { emptyStudy, newOption, type OptionDraft, type Study } from "./study";
import type { Report } from "./types";

const INDEX_KEY = "siteiq.projects.v1";
const projectKey = (id: string) => `siteiq.project.${id}`;
const FORMAT = "siteiq-project";

export interface RevisionSummary {
  verdict: string; maximumFar: number | null; capacity: number | null; ruleStatus: string; profileVersion: string | null;
  options: { name: string; floorArea: number | null; counted: number | null; remaining: number | null; envelope: number | null }[];
}
export interface Revision { id: string; name: string; savedAt: string; inputs: Record<string, unknown>; summary: RevisionSummary; study: Study }
export interface ProjectSummary { id: string; name: string; updatedAt: string }
export interface Project { study: Study; revisions: Revision[] }

const store = {
  get(key: string) { try { return localStorage.getItem(key); } catch { return null; } },
  set(key: string, value: string) { try { localStorage.setItem(key, value); return true; } catch { return false; } },
  remove(key: string) { try { localStorage.removeItem(key); } catch { /* Storage can be blocked in a private window. */ } },
};

export const newProjectId = () => `p${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;

/** Fill any field added since a project was saved, so older files keep opening. */
export function normaliseStudy(raw: Partial<Study>): Study {
  const options = (raw.options ?? []).map((o: Partial<OptionDraft>, i: number) => newOption(i, o));
  return { ...emptyStudy(), ...raw, overlays: raw.overlays ?? {}, options: options.length ? options : emptyStudy().options };
}

export function listProjects(): ProjectSummary[] {
  try { const parsed = JSON.parse(store.get(INDEX_KEY) ?? "[]"); return Array.isArray(parsed) ? parsed : []; } catch { return []; }
}

export function saveProject(id: string, study: Study, revisions: Revision[]) {
  store.set(projectKey(id), JSON.stringify({ study, revisions }));
  const summary = { id, name: study.projectName.trim() || "Untitled site", updatedAt: new Date().toISOString() };
  store.set(INDEX_KEY, JSON.stringify([summary, ...listProjects().filter((p) => p.id !== id)].slice(0, 30)));
}

export function loadProject(id: string): Project | null {
  try {
    const raw = store.get(projectKey(id));
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return { study: normaliseStudy(parsed.study ?? {}), revisions: Array.isArray(parsed.revisions) ? parsed.revisions : [] };
  } catch { return null; }
}

export function deleteProject(id: string) {
  store.remove(projectKey(id));
  store.set(INDEX_KEY, JSON.stringify(listProjects().filter((p) => p.id !== id)));
}

export const projectFileText = (study: Study, revisions: Revision[]) => JSON.stringify({ format: FORMAT, version: 1, savedAt: new Date().toISOString(), study, revisions }, null, 2);

export function parseProjectFile(text: string): Project {
  let parsed: { format?: string; study?: Partial<Study>; revisions?: Revision[] };
  try { parsed = JSON.parse(text); } catch { throw new Error("This file could not be read. Choose a SiteIQ project file."); }
  if (parsed?.format !== FORMAT || typeof parsed.study !== "object" || parsed.study === null) throw new Error("This is not a SiteIQ project file.");
  return { study: normaliseStudy(parsed.study), revisions: Array.isArray(parsed.revisions) ? parsed.revisions : [] };
}

export function downloadProject(study: Study, revisions: Revision[]) {
  const name = (study.projectName.trim() || "Untitled site").replace(/[^\w -]+/g, "").trim().replace(/\s+/g, "_") || "Project";
  const url = URL.createObjectURL(new Blob([projectFileText(study, revisions)], { type: "application/json" }));
  const a = document.createElement("a"); a.href = url; a.download = `${name}.siteiq`; a.click();
  URL.revokeObjectURL(url);
}

export function summariseReport(report: Report): RevisionSummary {
  return {
    verdict: report.verdict.code, maximumFar: report.maximum_far, capacity: report.maximum_far_area_m2, ruleStatus: report.application.source_status, profileVersion: report.application.profile_version ?? null,
    options: report.scenarios.map((s) => ({ name: s.name, floorArea: s.gross_concept_area_m2 ?? null, counted: s.far_counted_area_m2 ?? null, remaining: s.scenario_headroom_m2 ?? null, envelope: s.boundary_envelope?.area_m2 ?? null })),
  };
}

const flatten = (value: unknown, prefix = "", out: Record<string, string> = {}): Record<string, string> => {
  if (Array.isArray(value)) value.forEach((v, i) => flatten(v, `${prefix}[${i}]`, out));
  else if (value && typeof value === "object") Object.entries(value).forEach(([k, v]) => flatten(v, prefix ? `${prefix}.${k}` : k, out));
  else if (value !== null && value !== undefined && value !== "") out[prefix] = String(value);
  return out;
};

const SKIPPED = /^(location|boundary\.(points_m|holes_m|source_points_wgs84|source_holes_wgs84))/;
export interface Change { label: string; from: string; to: string }

/** Inputs that differ between two payloads, with location metadata and raw coordinates left out. */
export function diffInputs(before: unknown, after: unknown): Change[] {
  const a = flatten(before), b = flatten(after);
  return [...new Set([...Object.keys(a), ...Object.keys(b)])].filter((k) => !SKIPPED.test(k) && a[k] !== b[k]).sort().map((k) => ({ label: k.replace(/_/g, " ").replace(/\./g, " · "), from: a[k] ?? "—", to: b[k] ?? "—" }));
}

const number = (v: number | null | undefined, digits = 0) => (v == null ? "—" : v.toLocaleString("en-IN", { maximumFractionDigits: digits }));

/** Results that differ between two revisions, including a rule profile update. */
export function diffSummaries(before: RevisionSummary, after: RevisionSummary): Change[] {
  const out: Change[] = [];
  const add = (label: string, from: string, to: string) => { if (from !== to) out.push({ label, from, to }); };
  add("Status", before.verdict, after.verdict);
  add("Base FAR", number(before.maximumFar, 2), number(after.maximumFar, 2));
  add("Floor area capacity (m²)", number(before.capacity), number(after.capacity));
  add("Rule status", before.ruleStatus, after.ruleStatus);
  add("Rule profile version", before.profileVersion ?? "—", after.profileVersion ?? "—");
  const names = [...new Set([...before.options.map((o) => o.name), ...after.options.map((o) => o.name)])];
  for (const name of names) {
    const a = before.options.find((o) => o.name === name), b = after.options.find((o) => o.name === name);
    if (!a || !b) { out.push({ label: name, from: a ? "Present" : "—", to: b ? "Present" : "Removed" }); continue; }
    add(`${name}: floor area (m²)`, number(a.floorArea), number(b.floorArea));
    add(`${name}: counted for FAR (m²)`, number(a.counted), number(b.counted));
    add(`${name}: remaining (m²)`, number(a.remaining), number(b.remaining));
    add(`${name}: envelope (m²)`, number(a.envelope), number(b.envelope));
  }
  return out;
}
