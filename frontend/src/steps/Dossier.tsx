import { motion } from "motion/react";
import { useMemo, useState } from "react";
import { PlotCanvas } from "../components/PlotCanvas";
import { StatusMark, StatusTag } from "../components/StatusMark";
import { Note, Panel, Segmented } from "../components/ui";
import { api } from "../lib/api";
import { area, ratio, STATUS_LABEL, VERDICT_LABEL } from "../lib/format";
import type { Study } from "../lib/study";
import type { Check, CheckStatus, Report } from "../lib/types";

const ORDER: CheckStatus[] = ["FAIL", "NEEDS_INPUT", "REFER", "NOT_CONFIGURED", "PASS"];
const EXPORTS = [
  ["report-pdf", "Client report", "PDF, A4 landscape"], ["board-pdf", "Comparison board", "PDF, A3 landscape"], ["report-pptx", "Editable report", "PowerPoint"],
  ["board-pptx", "Editable board", "PowerPoint, A3"], ["envelopes-dxf", "Boundary and envelopes", "DXF, layered"], ["assessment-json", "Full assessment", "JSON"],
] as const;

export function Verdict({ report }: { report: Report }) {
  const { verdict } = report;
  return (
    <div data-testid="verdict" data-code={verdict.code} className="grid gap-6 bg-ink p-7 text-invert lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)] lg:items-end">
      <div>
        <p className="font-mono text-[10px] uppercase tracking-[0.12em] opacity-60">Status of this study</p>
        <p className="display mt-1 text-6xl leading-none">{VERDICT_LABEL[verdict.code]}</p>
        <p className="mt-4 max-w-xl text-[14px] leading-relaxed opacity-80">{verdict.message}</p>
      </div>
      <dl className="grid grid-cols-5 gap-3 border-t border-current/25 pt-4 lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0">
        {ORDER.map((s) => <div key={s}><dd className="display text-4xl tnum">{verdict.counts[s]}</dd><dt className="mt-1 font-mono text-[9.5px] uppercase leading-tight tracking-wide opacity-65">{STATUS_LABEL[s]}</dt></div>)}
      </dl>
    </div>
  );
}

export function DossierStep({ study, report, payload, stale, missing }: { study: Study; report: Report | null; payload: unknown; stale: boolean; missing: string[] }) {
  const [filter, setFilter] = useState<"open" | "all" | "fail">("open");
  const [downloading, setDownloading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const checks: Check[] = useMemo(() => {
    const all = [...(report?.compliance_checks ?? [])].sort((a, b) => ORDER.indexOf(a.status) - ORDER.indexOf(b.status));
    return filter === "all" ? all : filter === "fail" ? all.filter((c) => c.status === "FAIL") : all.filter((c) => c.status !== "PASS");
  }, [report, filter]);

  if (!report) return <p className="display max-w-2xl text-4xl leading-tight text-faint" data-testid="dossier-empty">The dossier is built from your study. Still needed: {missing.join(", ") || "a valid assessment"}.</p>;

  async function download(kind: string) {
    setDownloading(kind); setError(null);
    try { await api.download(kind, payload); } catch (e) { setError((e as Error).message); } finally { setDownloading(null); }
  }
  const capacity = report.maximum_far_area_m2;
  const widest = Math.max(capacity ?? 0, ...report.scenarios.map((s) => s.gross_concept_area_m2 ?? 0), 1);

  return (
    <div className="space-y-14">
      <Verdict report={report} />
      <Panel title="Options compared" aside={capacity != null ? <span className="font-mono text-xs">Base capacity {area(capacity)}</span> : <span className="text-xs text-soft">No FAR benchmark</span>}>
        <div className="overflow-x-auto scroll-quiet">
          <table className="w-full min-w-[860px] text-left text-[13px]" data-testid="comparison">
            <thead><tr className="border-b border-rule">{["Option", "Height", "Floors", "Setbacks", "Footprint", "Floor area", "FAR used", "Against capacity", "Remaining"].map((h, i) => <th key={h} scope="col" className={`mono-label pb-2 pl-3 font-normal first:pl-0 ${i === 3 || i === 0 || i === 7 ? "" : "text-right"}`}>{h}</th>)}</tr></thead>
            <tbody>
              {report.scenarios.map((s, i) => {
                const gross = s.gross_concept_area_m2 ?? 0;
                const over = (s.scenario_headroom_m2 ?? 0) < -0.5;
                return (
                  <tr key={i} className="border-b border-rule align-middle">
                    <th scope="row" className="display py-3 pr-4 text-xl font-normal">{s.name}</th>
                    <td className="text-right font-mono tnum">{s.height_m ?? "—"}</td>
                    <td className="text-right font-mono tnum">{s.floors ?? "—"}</td>
                    <td className="max-w-52 pl-4 pr-2 text-xs text-soft">{s.setback_summary}</td>
                    <td className="text-right font-mono tnum">{area(s.footprint_m2)}</td>
                    <td className="text-right font-mono tnum">{area(s.gross_concept_area_m2)}</td>
                    <td className="text-right font-mono tnum">{ratio(s.achieved_far_ratio)}</td>
                    <td className="w-52 pl-5 pr-3">
                      <div className="relative h-3 border-b border-rule" aria-hidden>
                        <motion.div className={`absolute inset-y-0 left-0 ${over ? "bg-ink" : "bg-soft"}`} initial={{ width: 0 }} animate={{ width: `${(gross / widest) * 100}%` }} />
                        {capacity != null && <span className="absolute -inset-y-1 w-px bg-ink" style={{ left: `${(capacity / widest) * 100}%` }} />}
                      </div>
                    </td>
                    <td className={`text-right font-mono tnum ${over ? "font-semibold" : ""}`}>{s.scenario_headroom_m2 != null ? `${s.scenario_headroom_m2 > 0 ? "+" : ""}${area(s.scenario_headroom_m2)}` : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs text-soft">Floor area is footprint × floors. FAR exclusions such as parking, stairs and lift shafts are not modelled, so real FAR will be lower.</p>
      </Panel>

      {study.boundary && (
        <Panel title="Envelopes on the plot">
          {study.boundary.illustrative && <div className="mb-4"><Note>This outline is illustrative, not a survey.</Note></div>}
          <div className="grid gap-5 md:grid-cols-2 2xl:grid-cols-4">
            {report.scenarios.map((s, i) => (
              <figure key={i} className="border border-rule bg-sheet">
                <div className="drafting-grid"><PlotCanvas compact points={study.boundary!.points} holes={study.boundary!.holes} roles={study.boundary!.roles} envelope={s.boundary_envelope} basement={s.basement_boundary_envelope} label={`${s.name} envelope`} /></div>
                <figcaption className="flex items-baseline justify-between border-t border-rule px-4 py-2.5"><span className="display text-lg">{s.name}</span><span className="font-mono text-xs tnum" data-testid={`envelope-area-${i}`}>{area(s.boundary_envelope?.area_m2)}</span></figcaption>
                {!!s.boundary_envelope?.warnings?.length && <p className="border-t border-rule px-4 py-2 text-xs leading-relaxed">{s.boundary_envelope.warnings.join(" ")}</p>}
                {s.boundary_envelope?.area_m2 == null && <p className="border-t border-rule px-4 py-2 text-xs leading-relaxed text-soft">{s.boundary_envelope?.message}</p>}
              </figure>
            ))}
          </div>
          <div className="mt-4 flex flex-wrap gap-6 font-mono text-[10.5px] text-soft">
            <span className="flex items-center gap-2"><svg width="18" height="12"><defs><pattern id="legend-hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="5" stroke="currentColor" strokeWidth=".8" /></pattern></defs><rect width="18" height="12" fill="url(#legend-hatch)" /></svg>Setback area</span>
            <span className="flex items-center gap-2"><svg width="24" height="4"><line x1="0" y1="2" x2="24" y2="2" stroke="currentColor" /></svg>Buildable envelope</span>
            <span className="flex items-center gap-2"><svg width="24" height="4"><line x1="0" y1="2" x2="24" y2="2" stroke="currentColor" strokeDasharray="6 3 1 3" /></svg>Basement limit</span>
          </div>
        </Panel>
      )}

      <Panel title="Compliance register" aside={<Segmented compact value={filter} onChange={setFilter} testId="register-filter" options={[{ value: "open", label: "Open items" }, { value: "fail", label: "Failures" }, { value: "all", label: "Everything" }]} />}>
        <ul className="divide-y divide-rule" data-testid="register">
          {checks.map((c, i) => (
            <li key={c.id + (c.option ?? "") + i} className="grid items-start gap-x-6 gap-y-1 py-3 md:grid-cols-[8rem_minmax(0,14rem)_minmax(0,1fr)]">
              <StatusTag status={c.status} />
              <span className="text-[13px] font-medium">{c.title}{c.option && <span className="block font-mono text-[10.5px] font-normal text-soft">{c.option}</span>}</span>
              <span className="text-[13px] leading-relaxed text-soft">{c.message}{c.source?.url && <> <a href={c.source.url} target="_blank" rel="noreferrer noopener" className="whitespace-nowrap text-ink underline underline-offset-3">{c.source.notification ?? "Source"}</a></>}</span>
            </li>
          ))}
          {!checks.length && <li className="flex items-center gap-2 py-4 text-sm text-soft"><StatusMark status="PASS" />Nothing in this view.</li>}
        </ul>
      </Panel>

      <Panel title="Issue" aside={stale ? <span className="text-xs">Recalculating. Exports wait for the latest figures.</span> : <span className="font-mono text-[10.5px] text-soft">Set {report.input_fingerprint}</span>}>
        {report.verdict.code !== "READY_FOR_REVIEW" && <div className="mb-5"><Note>Every export carries the status above, so nobody reads it as a sanction-ready study.</Note></div>}
        {error && <div className="mb-5"><Note tone="strong">{error}</Note></div>}
        <div className="grid gap-px border border-rule bg-rule sm:grid-cols-2 lg:grid-cols-3">
          {EXPORTS.map(([kind, title, format]) => {
            const unavailable = kind === "envelopes-dxf" && !study.boundary;
            return (
              <button key={kind} type="button" data-testid={`export-${kind}`} disabled={stale || unavailable || !!downloading} onClick={() => download(kind)} className="group flex items-center justify-between gap-4 bg-sheet p-5 text-left transition-colors hover:bg-ink hover:text-invert disabled:opacity-40 disabled:hover:bg-sheet disabled:hover:text-ink">
                <span><span className="display block text-2xl leading-tight">{title}</span><span className="font-mono text-[11px] opacity-60">{unavailable ? "Needs a boundary" : format}</span></span>
                <span aria-hidden className="font-mono transition-transform group-hover:translate-y-0.5">{downloading === kind ? "…" : "↓"}</span>
              </button>
            );
          })}
        </div>
      </Panel>
    </div>
  );
}
