import { positive } from "./format";
import { perimeter, shoelace } from "./geometry";
import type { EdgeRole, LocationResult, Point } from "./types";

export interface OptionDraft {
  id: string; name: string; height: string; floors: string; footprint: string; stilt: boolean; stiltHeight: string; manualSetback: string; basements: string; manualBasementFront: string; manualBasementSide: string;
}
export interface OverlayDraft { status: "unknown" | "absent" | "present"; edge: string; depth: string; drainClass: "" | "primary" | "secondary" | "tertiary"; lineKv?: string }
export interface AppliedBoundary {
  sourceFile: string; sourceType: string; sourceUnits?: string; scale?: number | null; fingerprint?: string; candidateId?: string; illustrative?: boolean;
  points: Point[]; holes: Point[][]; area: number; perimeter: number; convex: boolean; notes: string[]; wgs84?: Point[]; holesWgs84?: Point[][];
  useComputedArea: boolean; roles: Record<number, EdgeRole>; roadWidths: Record<number, string>;
}
export interface Study {
  projectName: string; client: string; address: string; mapUrl: string; coordinates: string; location: LocationResult | null; authorityKey: string; authorityConfirmed: boolean;
  category: string; zoneConfirmed: boolean; surroundingZone: string; proposedUse: string; siteArea: string; stated: string; roadWidth: string; roadSource: "unknown" | "notified" | "survey" | "measured";
  deduction: string; ring: "" | "I" | "II" | "III"; units: string; unitArea: string; landStatus: "unknown" | "converted" | "not_converted"; priorSanction: "unknown" | "none" | "exists"; approvalPath: string;
  frontage: string; depth: string; boundary: AppliedBoundary | null; overlays: Record<string, OverlayDraft>; options: OptionDraft[];
}
export const OVERLAYS: [string, string][] = [
  ["lake", "Lake or tank"], ["drain", "Drain or rajakaluve"], ["ht_line", "High-tension power line"], ["airport", "Airport height zone"], ["heritage", "Protected monument"],
  ["railway", "Railway land"], ["defence", "Defence establishment"], ["highway", "National or state highway"], ["flood_prone", "Flood-prone or low-lying land"], ["road_widening", "Road widening or master-plan road"],
];
export const USES = ["Residential apartments", "Individual house / villa", "Commercial / office", "Mixed use", "Institutional / other", "Industrial / warehouse", "Public / semi-public use", "Parking structure"];

let counter = 0;
export const newOption = (index: number, seed: Partial<OptionDraft> = {}): OptionDraft => ({
  id: `opt-${Date.now()}-${counter++}`, name: `Option ${String(index + 1).padStart(2, "0")}`, height: "", floors: "", footprint: "", stilt: false, stiltHeight: "", manualSetback: "", basements: "0", manualBasementFront: "", manualBasementSide: "", ...seed,
});
export const emptyStudy = (): Study => ({
  projectName: "", client: "", address: "", mapUrl: "", coordinates: "", location: null, authorityKey: "", authorityConfirmed: false, category: "", zoneConfirmed: false, surroundingZone: "", proposedUse: USES[0],
  siteArea: "", stated: "", roadWidth: "", roadSource: "unknown", deduction: "", ring: "", units: "", unitArea: "", landStatus: "unknown", priorSanction: "unknown", approvalPath: "Not sure / needs confirmation", frontage: "", depth: "", boundary: null,
  overlays: {}, options: [newOption(0), newOption(1)],
});

/** Area in force: the applied boundary if it is in use, otherwise the typed figure. Never a default. */
export const effectiveArea = (s: Study): number | null => (s.boundary?.useComputedArea ? s.boundary.area : positive(s.siteArea));

/** What still prevents a calculation. An empty list means an assessment can run. */
export const missing = (s: Study, hasRules: boolean): string[] => {
  const out: string[] = [];
  if (!s.authorityKey) out.push("planning authority");
  if (hasRules && !s.category) out.push("land-use category");
  if (effectiveArea(s) == null) out.push("plot area");
  if (positive(s.roadWidth) == null) out.push("road width");
  return out;
};

const edgesWithRole = (b: AppliedBoundary, role: EdgeRole) => Object.entries(b.roles).filter(([, r]) => r === role).map(([i]) => Number(i)).sort((x, y) => x - y);

export const toPayload = (s: Study) => {
  const b = s.boundary;
  const overlays: Record<string, unknown> = {};
  for (const [key] of OVERLAYS) {
    const o = s.overlays[key];
    if (!o || o.status === "unknown") continue;
    overlays[key] = { status: o.status, edge: o.status === "present" && o.edge !== "" ? Number(o.edge) : null, extra_setback_m: o.status === "present" ? positive(o.depth) : null, drain_class: key === "drain" && o.drainClass ? o.drainClass : null, line_kv: key === "ht_line" && o.lineKv ? o.lineKv : null };
  }
  const location = s.location ? JSON.parse(JSON.stringify(s.location)) : null;
  return {
    project_name: s.projectName.trim() || "Untitled site", client: s.client.trim(), address: s.address.trim(), map_url: s.mapUrl.trim(), coordinates: s.coordinates.trim(),
    authority_key: s.authorityKey, authority_confirmed: s.authorityConfirmed, land_use_category: s.category || "Not configured", zone_confirmed: s.zoneConfirmed, surrounding_zone: s.surroundingZone || null,
    proposed_use: s.proposedUse, site_area_m2: effectiveArea(s) ?? 0, site_area_source: b?.useComputedArea ? "imported polyline area" : "user-entered survey/title area", area_stated_m2: positive(s.stated),
    road_width_m: positive(s.roadWidth) ?? 0, road_width_source: s.roadSource, road_edges: b ? Object.entries(b.roadWidths).filter(([i, w]) => positive(w) != null && b.roles[Number(i)] === "road").map(([i, w]) => ({ edge: Number(i), width_m: positive(w)! })) : [],
    statutory_deduction_pct: positive(s.deduction), frontage_m: positive(s.frontage), depth_m: positive(s.depth), approval_path: s.approvalPath, rmp_ring: s.ring || null, dwelling_units: positive(s.units) ? Math.round(positive(s.units)!) : null, average_unit_area_m2: positive(s.unitArea),
    land_status: s.landStatus, prior_sanction: s.priorSanction, overlays,
    scenarios: s.options.map((o, i) => ({
      name: o.name.trim() || `Option ${i + 1}`, height_m: positive(o.height), floors: positive(o.floors) ? Math.round(positive(o.floors)!) : null, footprint_m2: positive(o.footprint), stilt: o.stilt, stilt_height_m: o.stilt ? positive(o.stiltHeight) : null,
      setback_mode: positive(o.manualSetback) ? "manual" : "automatic", manual_all_round_setback_m: positive(o.manualSetback), basement_levels: Math.max(0, Math.round(Number(o.basements) || 0)),
      basement_setback_mode: positive(o.manualBasementFront) && positive(o.manualBasementSide) ? "manual" : "automatic", manual_basement_front_m: positive(o.manualBasementFront), manual_basement_nonfront_m: positive(o.manualBasementSide),
    })),
    boundary: b ? {
      source_file: b.sourceFile, source_type: b.sourceType, source_units: b.sourceUnits ?? null, scale_to_m: b.scale ?? null, source_fingerprint: b.fingerprint ?? null, candidate_id: b.candidateId ?? null,
      points_m: b.points, holes_m: b.holes, area_m2: b.area, perimeter_m: b.perimeter, vertex_count: b.points.length, is_convex: b.convex, validation_notes: b.notes, use_computed_area: b.useComputedArea,
      front_edges: edgesWithRole(b, "road"), rear_edges: edgesWithRole(b, "rear"), source_points_wgs84: b.wgs84 ?? null, source_holes_wgs84: b.holesWgs84 ?? null,
    } : null,
    location,
  };
};

// Illustrative figures carried over from the repository's Nandi sample. The polygon is drawn for demonstration, not surveyed.
const NANDI_POINTS: Point[] = [[0, 0], [33, 2], [37, 34], [31, 68], [2, 62]];
export const nandiSample = (): Study => ({
  ...emptyStudy(), projectName: "Nandi Housing", client: "Sample study", address: "Southern Bengaluru (sample)", coordinates: "12.871003, 77.569919", authorityKey: "bengaluru_rmp2015", category: "Residential (Main)", roadWidth: "18.5", roadSource: "measured", stated: "2200",
  boundary: {
    sourceFile: "Illustrative outline (not a survey)", sourceType: "sample", illustrative: true, points: NANDI_POINTS, holes: [], area: shoelace(NANDI_POINTS), perimeter: perimeter(NANDI_POINTS), convex: true, notes: ["Illustrative outline for demonstration. It is not a survey."],
    useComputedArea: true, roles: { 0: "road", 2: "rear" }, roadWidths: { 0: "18.5" },
  },
  options: [
    newOption(0, { height: "12", floors: "4", footprint: "1483" }),
    newOption(1, { height: "15", floors: "5", footprint: "1271" }),
    newOption(2, { height: "18", floors: "6", footprint: "1106", basements: "1" }),
  ],
});
