export type Point = [number, number];
export type CheckStatus = "PASS" | "FAIL" | "NEEDS_INPUT" | "REFER" | "NOT_CONFIGURED";
export type EdgeRole = "road" | "rear" | "left" | "right" | "side";

export interface AuthoritySummary { key: string; name: string; status?: string; group?: string | null; has_rules: boolean; source_status: string; scope_note?: string }
export interface Meta { version: string; authorities: AuthoritySummary[] }
export interface RuleSource { id?: string; title?: string; notification?: string; date?: string; clause?: string; document_page?: string; status?: string; url?: string }
export interface AuthorityDetail {
  key: string; name: string; scope_note?: string; has_rules: boolean; profile_name?: string; profile_status?: string; source_status: string;
  status_problem?: string | null; has_apartment_rings: boolean; categories: { key: string; label: string; table?: string; method?: string }[]; sources: RuleSource[];
}
export interface LocationResult {
  coordinates: { latitude: number; longitude: number; text: string; method: string };
  location_source: string; geocoded_address?: string; map_url?: string;
  authority: { key?: string | null; label?: string; status?: string; reason?: string; confidence?: string };
  suggested_authority_key?: string | null;
  zone?: { value?: string; status?: string; reason?: string };
  approval_route?: { suggested_value?: string; reason?: string };
  input_coordinate_comparison?: { distance_km: number; mismatch: boolean } | null;
  map_link_resolution?: { precision?: string | null; warning?: string | null };
  public_sources?: { title?: string; url?: string; note?: string }[];
  [key: string]: unknown;
}
export interface Candidate {
  candidate_id: string; label: string; points: Point[]; closed: boolean; source_type: string; source_units?: string; scale_to_m: number | null; notes?: string;
  holes?: Point[][]; source_points_wgs84?: Point[]; source_holes_wgs84?: Point[][]; source_location_point_wgs84?: Point | null; source_location_method?: string; [key: string]: unknown;
}
export interface ParsedFile { filename: string; fingerprint: string; candidates: Candidate[]; meta: { format?: string; units?: string; warnings?: string[]; scale_to_m?: number | null } }
export interface Validation { status: string; message: string; area_m2?: number; perimeter_m?: number; vertex_count?: number; is_convex?: boolean; notes?: string[]; hole_count?: number }
export interface ValidatedBoundary { valid: boolean; validation: Validation; points_m?: Point[]; holes_m?: Point[][]; edges?: { edge_index: number; length: number }[] }
export interface Geometry { type: "Polygon" | "MultiPolygon"; coordinates: number[][][] | number[][][][] }
export interface Envelope { status: string; message?: string; area_m2?: number | null; geometry?: Geometry | null; component_count?: number; warnings?: string[]; has_narrow_neck?: boolean; is_split?: boolean }
export interface Check { id: string; group: string; title: string; status: CheckStatus; message: string; source?: RuleSource | null; option?: string | null; value?: unknown }
export interface ScenarioResult {
  name: string; height_m?: number | null; floors?: number | null; footprint_m2?: number | null; footprint_source?: string; gross_concept_area_m2?: number | null; far_counted_area_m2?: number | null; far_excluded_m2?: number | null;
  achieved_far_ratio?: number | null; far_ratio_basis?: string; scenario_headroom_m2?: number | null; setback_summary?: string; basement_setback_summary?: string; basement_levels?: number; stilt?: boolean;
  boundary_envelope?: Envelope; basement_boundary_envelope?: Envelope; far_capacity_m2?: number | null;
}
export interface FarResult {
  status: string; message?: string; category?: string; table?: string; maximum_far?: number | null; maximum_far_area_m2?: number | null; far_calculation_area_m2?: number;
  profile_name?: string; conditions?: string[]; selected_path?: string | null; source?: RuleSource | null; coverage?: { coverage_pct?: number | null; message?: string };
  matched_rule?: { details?: Record<string, unknown>; matched_bands?: Record<string, unknown>[]; gross_site_area_m2?: number } | null;
  premium_far?: { status?: string; message?: string; additional_far_candidate?: number; additional_floor_area_candidate_m2?: number; potential_total_far_candidate?: number; premium_only_additional_far?: number; premium_only_additional_area_m2?: number; charge_estimate?: { estimated_charge_inr: number; notional_site_area_m2: number; note: string; guidance_value_per_m2: number } | null } | null;
}
export interface Report {
  project: string; application: { version: string; assessment_date: string; source_status: string; profile_version?: string };
  site: Record<string, unknown> & { site_area_m2: number; road_width_m: number; authority?: string };
  far: FarResult; maximum_far: number | null; maximum_far_area_m2: number | null; scenarios: ScenarioResult[]; compliance_checks: Check[];
  verdict: { code: "BLOCKED" | "INCOMPLETE" | "PROVISIONAL" | "READY_FOR_REVIEW"; message: string; counts: Record<CheckStatus, number>; total: number };
  boundary_analysis?: { geometry: Geometry; front_edges: number[]; rear_edges: number[]; dimension_range?: { depth_min_m: number; depth_max_m: number; width_min_m: number; width_max_m: number } | null } | null;
  road_widening?: { edge: number; depth_m: number; area_taken_m2: number; capacity_if_land_excluded_m2?: number } | null; input_fingerprint: string;
}
