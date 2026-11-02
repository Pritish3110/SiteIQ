import { AnimatePresence, motion } from "motion/react";
import { PlotCanvas } from "../components/PlotCanvas";
import { StatusMark } from "../components/StatusMark";
import { Button, Check, Field, Note } from "../components/ui";
import { area, ratio } from "../lib/format";
import { newOption, type OptionDraft, type Study } from "../lib/study";
import type { Report } from "../lib/types";

export function OptionsStep({ study, set, report }: { study: Study; set: (p: Partial<Study>) => void; report: Report | null }) {
  const update = (id: string, patch: Partial<OptionDraft>) => set({ options: study.options.map((o) => (o.id === id ? { ...o, ...patch } : o)) });
  return (
    <div>
      <div className="grid gap-6 lg:grid-cols-2 2xl:grid-cols-3">
        <AnimatePresence initial={false}>
          {study.options.map((option, index) => {
            const result = report?.scenarios[index];
            const failures = report?.compliance_checks.filter((c) => c.option === result?.name && c.status === "FAIL") ?? [];
            return (
              <motion.article key={option.id} layout initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, scale: 0.98 }} data-testid={`option-${index}`} className="flex flex-col border border-rule bg-sheet">
                <header className="flex items-center justify-between gap-3 border-b border-rule px-5 py-3">
                  <input aria-label="Option name" value={option.name} onChange={(e) => update(option.id, { name: e.target.value })} className="display min-w-0 flex-1 bg-transparent text-2xl outline-none" />
                  {study.options.length > 1 && <button type="button" aria-label={`Remove ${option.name}`} data-testid={`remove-option-${index}`} onClick={() => set({ options: study.options.filter((o) => o.id !== option.id) })} className="px-1 font-mono text-xs text-soft hover:text-ink">Remove</button>}
                </header>
                {study.boundary && <div className="drafting-grid border-b border-rule"><PlotCanvas compact points={study.boundary.points} holes={study.boundary.holes} roles={study.boundary.roles} envelope={result?.boundary_envelope} basement={result?.basement_boundary_envelope} label={`${option.name} envelope`} /></div>}
                <div className="grid grid-cols-2 gap-x-5 gap-y-5 p-5">
                  <Field label="Height" type="number" unit="m" value={option.height} onChange={(v) => update(option.id, { height: v })} testId={`height-${index}`} />
                  <Field label="Floors" type="number" value={option.floors} onChange={(v) => update(option.id, { floors: v })} testId={`floors-${index}`} />
                  <Field label="Footprint" type="number" unit="m²" value={option.footprint} onChange={(v) => update(option.id, { footprint: v })} testId={`footprint-${index}`} placeholder={study.boundary ? "Auto" : ""} />
                  <Field label="Basement levels" type="number" value={option.basements} onChange={(v) => update(option.id, { basements: v })} testId={`basements-${index}`} />
                  <div className="col-span-2 grid grid-cols-2 items-end gap-x-5">
                    <Check label="Stilt floor" checked={option.stilt} onChange={(v) => update(option.id, { stilt: v })} testId={`stilt-${index}`} />
                    <Field label="Stilt height" type="number" unit="m" value={option.stiltHeight} onChange={(v) => update(option.id, { stiltHeight: v })} disabled={!option.stilt} testId={`stilt-height-${index}`} />
                  </div>
                  <details className="col-span-2 group/a" data-testid={`far-details-${index}`}>
                    <summary className="mono-label cursor-pointer list-none hover:text-ink"><span className="inline-block transition-transform group-open/a:rotate-90">›</span> FAR exclusions and floor schedule</summary>
                    <div className="mt-4 grid grid-cols-2 gap-4">
                      <Field label="Core, per floor" type="number" unit="m²" value={option.corePerFloor ?? ""} onChange={(v) => update(option.id, { corePerFloor: v })} testId={`core-${index}`} hint="Stairs, lifts and ducts, where the rule allows." />
                      <Field label="Parking, in total" type="number" unit="m²" value={option.parking ?? ""} onChange={(v) => update(option.id, { parking: v })} testId={`parking-${index}`} hint="Parking inside the floor area." />
                    </div>
                    <div className="mt-5 space-y-3">
                      {(option.schedule ?? []).map((row, r) => (
                        <div key={r} className="grid grid-cols-[1.3fr_0.7fr_1fr_auto] items-end gap-3" data-testid={`schedule-row-${index}-${r}`}>
                          <Field label="Level" value={row.name} placeholder="Typical" onChange={(v) => update(option.id, { schedule: option.schedule.map((x, i) => (i === r ? { ...x, name: v } : x)) })} />
                          <Field label="Floors" type="number" value={row.floors} onChange={(v) => update(option.id, { schedule: option.schedule.map((x, i) => (i === r ? { ...x, floors: v } : x)) })} testId={`schedule-floors-${index}-${r}`} />
                          <Field label="Area each" type="number" unit="m²" value={row.area} onChange={(v) => update(option.id, { schedule: option.schedule.map((x, i) => (i === r ? { ...x, area: v } : x)) })} testId={`schedule-area-${index}-${r}`} />
                          <button type="button" aria-label={`Remove level ${r + 1}`} className="pb-2 font-mono text-xs text-soft hover:text-ink" onClick={() => update(option.id, { schedule: option.schedule.filter((_, i) => i !== r) })}>×</button>
                        </div>
                      ))}
                      <button type="button" data-testid={`add-level-${index}`} className="text-[13px] underline underline-offset-4" onClick={() => update(option.id, { schedule: [...(option.schedule ?? []), { name: "", floors: "", area: "" }] })}>Add a level</button>
                      {(option.schedule ?? []).length > 0 && <p className="text-xs text-soft">The schedule replaces footprint × floors for this option.</p>}
                    </div>
                  </details>
                  <details className="col-span-2 group">
                    <summary className="mono-label cursor-pointer list-none hover:text-ink"><span className="inline-block transition-transform group-open:rotate-90">›</span> What-if setbacks</summary>
                    <div className="mt-4 grid grid-cols-3 gap-4">
                      <Field label="All round" type="number" unit="m" value={option.manualSetback} onChange={(v) => update(option.id, { manualSetback: v })} testId={`manual-setback-${index}`} />
                      <Field label="Basement front" type="number" unit="m" value={option.manualBasementFront} onChange={(v) => update(option.id, { manualBasementFront: v })} />
                      <Field label="Basement sides" type="number" unit="m" value={option.manualBasementSide} onChange={(v) => update(option.id, { manualBasementSide: v })} />
                    </div>
                    <p className="mt-2 text-xs text-soft">These replace the rule for this option and are labelled as your assumption.</p>
                  </details>
                </div>
                {result && (
                  <div className="mt-auto border-t border-ink p-5">
                    <div className="mb-3 grid grid-cols-3 gap-3">
                      <div><p className="mono-label">Floor area</p><p className="mt-0.5 font-mono text-[13px] tnum" data-testid={`gross-${index}`}>{area(result.gross_concept_area_m2)}</p></div>
                      <div><p className="mono-label">FAR used</p><p className="mt-0.5 font-mono text-[13px] tnum">{ratio(result.achieved_far_ratio)}</p></div>
                      <div><p className="mono-label">Remaining</p><p className="mt-0.5 font-mono text-[13px] tnum" data-testid={`headroom-${index}`}>{result.scenario_headroom_m2 != null ? `${result.scenario_headroom_m2 > 0 ? "+" : ""}${area(result.scenario_headroom_m2)}` : "—"}</p></div>
                    </div>
                    <p className="text-xs leading-relaxed text-soft">Setbacks: {result.setback_summary ?? "Not determined"}{result.footprint_source ? ` · Footprint from ${result.footprint_source}` : ""}</p>
                    {failures.length > 0 && <ul className="mt-3 space-y-1.5" data-testid={`failures-${index}`}>{failures.map((f) => <li key={f.id} className="flex gap-2 text-[12.5px] font-medium leading-snug"><StatusMark status="FAIL" size={13} /><span>{f.message}</span></li>)}</ul>}
                  </div>
                )}
              </motion.article>
            );
          })}
        </AnimatePresence>
      </div>
      <div className="mt-6 flex items-center gap-5">
        <Button variant="line" disabled={study.options.length >= 4} onClick={() => set({ options: [...study.options, newOption(study.options.length)] })} data-testid="add-option">Add an option</Button>
        {!study.boundary && <Note>Apply a boundary to see each option's envelope.</Note>}
      </div>
    </div>
  );
}
