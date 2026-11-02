import { useMemo } from "react";
import { Check, Field, Note, Panel, Row, Segmented, Select } from "../components/ui";
import { area, SOURCE_STATUS_LABEL } from "../lib/format";
import { edgeLengths } from "../lib/geometry";
import { OVERLAYS, USES, type OverlayDraft, type Study } from "../lib/study";
import type { AuthorityDetail, Meta } from "../lib/types";

const ROUTES = ["Not sure / needs confirmation", "New single-plot approval under Chapter 6-A", "Existing sanctioned plan / modification", "Development plan / layout", "Group housing / residential development-plan candidate", "Non-residential development-plan candidate", "Other"];

export function ControlsStep({ study, set, meta, detail }: { study: Study; set: (p: Partial<Study>) => void; meta: Meta; detail: AuthorityDetail | null }) {
  const options = useMemo(() => [...meta.authorities].sort((a, b) => Number(b.has_rules) - Number(a.has_rules)).map((a) => ({
    value: a.key, label: a.name, note: SOURCE_STATUS_LABEL[a.source_status] ?? a.source_status, group: a.has_rules ? "Rules configured" : "No rules yet",
  })), [meta]);
  const category = detail?.categories.find((c) => c.label === study.category);
  const lengths = study.boundary ? edgeLengths(study.boundary.points) : [];
  const setOverlay = (key: string, patch: Partial<OverlayDraft>) => {
    const current: OverlayDraft = study.overlays[key] ?? { status: "unknown", edge: "", depth: "", drainClass: "" };
    set({ overlays: { ...study.overlays, [key]: { ...current, ...patch } } });
  };
  const inherits = category?.method === "inherit_surrounding_zone";

  return (
    <div className="space-y-14">
      <div className="grid gap-x-14 gap-y-12 xl:grid-cols-2">
        <Panel title="Jurisdiction and land use">
          <div className="space-y-6">
            <Select label="Planning authority" value={study.authorityKey} onChange={(v) => set({ authorityKey: v, category: "", surroundingZone: "", authorityConfirmed: false, zoneConfirmed: false, ring: "" })} options={options} placeholder="Choose the authority" testId="authority-select"
              hint={study.location ? "Suggested by the location lookup. Change it if the official map says otherwise." : undefined} />
            {detail && !detail.has_rules && <Note tone="strong" testId="no-rules">No rules are configured for {detail.name}. SiteIQ will not borrow another authority's FAR, so no FAR will be given.</Note>}
            {detail?.profile_status && <Note>{detail.profile_status}</Note>}
            {detail?.has_rules && (
              <>
                <Select label="Land-use category" value={study.category} onChange={(v) => set({ category: v, surroundingZone: "", zoneConfirmed: false })} testId="category-select" placeholder="Choose from this authority's table"
                  options={detail.categories.map((c) => ({ value: c.label ?? c.key, label: c.label ?? c.key, note: c.table }))} />
                {inherits && <Select label="Official surrounding zone" value={study.surroundingZone} onChange={(v) => set({ surroundingZone: v })} options={detail.categories.filter((c) => ["area_cap_and_road_width", "road_width", "plot_area", "fixed"].includes(c.method ?? "")).map((c) => ({ value: c.label, label: c.label }))} />}
                <Check label="I have checked this category against the notified land-use map" checked={study.zoneConfirmed} onChange={(v) => set({ zoneConfirmed: v })} testId="confirm-zone" />
              </>
            )}
            <Select label="Proposed use" value={study.proposedUse} onChange={(v) => set({ proposedUse: v })} options={USES.map((u) => ({ value: u, label: u }))} testId="use-select" />
            <Select label="Approval route" value={study.approvalPath} onChange={(v) => set({ approvalPath: v })} options={ROUTES.map((u) => ({ value: u, label: u }))} />
            {detail?.has_apartment_rings && <Segmented label="RMP ring" value={study.ring || "none"} onChange={(v) => set({ ring: v === "none" ? "" : (v as Study["ring"]) })} testId="ring" options={[{ value: "none", label: "Not known" }, { value: "I", label: "Ring I" }, { value: "II", label: "Ring II" }, { value: "III", label: "Ring III" }]} />}
          </div>
        </Panel>

        <Panel title="Plot and road">
          <div className="space-y-6">
            {study.boundary?.useComputedArea ? <Row k="Plot area, from the boundary" v={area(study.boundary.area, 2)} /> : (
              <Field label="Plot area" type="number" unit="m²" value={study.siteArea} onChange={(v) => set({ siteArea: v })} testId="site-area" hint="From the title or survey. Applying a boundary replaces this." />
            )}
            <div className="space-y-5">
              <Field label="Abutting road width" type="number" unit="m" value={study.roadWidth} onChange={(v) => set({ roadWidth: v })} testId="road-width" />
              <Segmented label="Where is that width from?" compact value={study.roadSource} onChange={(v) => set({ roadSource: v })} testId="road-source" options={[{ value: "unknown", label: "Unknown" }, { value: "notified", label: "Notified" }, { value: "survey", label: "Survey" }, { value: "measured", label: "Measured" }]} />
            </div>
            {!study.boundary && (
              <div className="grid gap-6 sm:grid-cols-2">
                <Field label="Frontage" type="number" unit="m" value={study.frontage} onChange={(v) => set({ frontage: v })} testId="frontage" hint="Needed for percentage setbacks without a boundary." />
                <Field label="Depth" type="number" unit="m" value={study.depth} onChange={(v) => set({ depth: v })} testId="depth" />
              </div>
            )}
            <div className="grid gap-6 sm:grid-cols-2">
              <Field label="Dwelling units" type="number" value={study.units} onChange={(v) => set({ units: v })} testId="units" hint="For parking, apartment and RERA checks." />
              <Field label="Average unit area" type="number" unit="m²" value={study.unitArea} onChange={(v) => set({ unitArea: v })} testId="unit-area" />
            </div>
            <Field label="Guidance value" type="number" unit="₹/m²" value={study.guidanceValue} onChange={(v) => set({ guidanceValue: v })} testId="guidance-value" hint="Optional. Used only to estimate a Premium FAR charge." />
            <Field label="Reservation to test" type="number" unit="%" value={study.deduction} onChange={(v) => set({ deduction: v })} testId="deduction" hint="Optional what-if, shown as your assumption. Rules with their own deduction apply it automatically." />
            <div className="flex flex-wrap gap-x-8 gap-y-5">
              <Segmented label="Land conversion" compact value={study.landStatus} onChange={(v) => set({ landStatus: v })} testId="land-status" options={[{ value: "unknown", label: "Unknown" }, { value: "converted", label: "Converted" }, { value: "not_converted", label: "Not converted" }]} />
              <Segmented label="Earlier sanction or layout" compact value={study.priorSanction} onChange={(v) => set({ priorSanction: v })} testId="prior-sanction" options={[{ value: "unknown", label: "Unknown" }, { value: "none", label: "None" }, { value: "exists", label: "Exists" }]} />
            </div>
          </div>
        </Panel>
      </div>

      <Panel title="Constraints on the site" aside={<span className="text-xs text-soft">SiteIQ has no official layers for these. Unknown stays open on the register.</span>}>
        <div className="divide-y divide-rule">
          {OVERLAYS.map(([key, label]) => {
            const o = study.overlays[key] ?? { status: "unknown" as const, edge: "", depth: "", drainClass: "" as const };
            return (
              <div key={key} data-testid={`overlay-${key}`} className="grid items-center gap-x-6 gap-y-3 py-3 lg:grid-cols-[minmax(0,1.1fr)_auto_minmax(0,1.6fr)]">
                <span className="text-[13.5px]">{label}</span>
                <Segmented compact value={o.status} onChange={(v) => setOverlay(key, { status: v })} options={[{ value: "unknown", label: "Unknown" }, { value: "absent", label: "Clear" }, { value: "present", label: "Affects site" }]} />
                {o.status === "present" ? (
                  <div className="grid gap-4 sm:grid-cols-3">
                    {key === "drain" ? <Select label="Class" value={o.drainClass} onChange={(v) => setOverlay(key, { drainClass: v as OverlayDraft["drainClass"] })} options={["primary", "secondary", "tertiary"].map((c) => ({ value: c, label: c[0].toUpperCase() + c.slice(1) }))} testId="drain-class" /> : key === "ht_line" ? <Select label="Voltage" value={o.lineKv ?? ""} onChange={(v) => setOverlay(key, { lineKv: v })} options={["LT", "11", "33", "66", "110", "220", "400"].map((v) => ({ value: v, label: v === "LT" ? "L.T." : `${v} kV` }))} testId="line-kv" /> : <span className="hidden sm:block" />}
                    <Select label="Along edge" value={o.edge} onChange={(v) => setOverlay(key, { edge: v })} disabled={!lengths.length} placeholder={lengths.length ? "Choose" : "Needs boundary"} options={lengths.slice(0, 60).map((l, i) => ({ value: String(i), label: `Edge ${i + 1}`, note: `${l.toFixed(1)} m` }))} />
                    <Field label="No-build depth" type="number" unit="m" value={o.depth} onChange={(v) => setOverlay(key, { depth: v })} />
                  </div>
                ) : <span />}
              </div>
            );
          })}
        </div>
      </Panel>
    </div>
  );
}
