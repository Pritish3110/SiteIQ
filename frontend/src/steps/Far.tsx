import { motion } from "motion/react";
import { CountUp, Note, Panel, Row } from "../components/ui";
import { area, humanise, metres, ratio, SOURCE_STATUS_LABEL } from "../lib/format";
import type { Report } from "../lib/types";

const band = (b: Record<string, unknown>) => {
  const low = b.min as number | undefined, high = b.max as number | null | undefined;
  const lo = low ? `${b.min_exclusive ? "above" : "from"} ${low}` : "up to";
  return high == null ? `${lo}` : low ? `${lo} to ${high}` : `${lo} ${high}`;
};

export function FarStep({ report, missing }: { report: Report | null; missing: string[] }) {
  if (!report) return <p className="display max-w-2xl text-4xl leading-tight text-faint" data-testid="far-empty">Enter the {missing.join(", ") || "inputs"} on the earlier sheets. No FAR is shown until a rule actually matches.</p>;
  const far = report.far;
  const details = far.matched_rule?.details ?? {};
  const bands = far.matched_rule?.matched_bands ?? [];
  const hasFar = far.maximum_far != null;
  return (
    <div className="grid gap-x-16 gap-y-12 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
      <div className="space-y-12">
        {hasFar ? (
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
            <p className="mono-label">Maximum base FAR, candidate</p>
            <p className="display mt-1 text-[clamp(6rem,13vw,11rem)] leading-[0.95]"><CountUp value={far.maximum_far!} digits={2} testId="far-value" /></p>
            <div className="mt-8 grid gap-8 border-t border-rule pt-5 sm:grid-cols-3">
              <div><p className="mono-label">Site area</p><p className="display mt-1 text-3xl tnum" data-testid="far-area">{area(far.far_calculation_area_m2)}</p></div>
              <div><p className="mono-label">Floor area capacity</p><p className="display mt-1 text-3xl tnum" data-testid="far-capacity">{area(far.maximum_far_area_m2)}</p></div>
              <div><p className="mono-label">Limited by</p><p className="display mt-1 text-3xl">{humanise(String(details.limiting_factor ?? "table rule"))}</p></div>
            </div>
          </motion.div>
        ) : (
          <div data-testid="far-unresolved">
            <p className="mono-label">No FAR given</p>
            <p className="display mt-2 text-5xl leading-tight">SiteIQ did not guess.</p>
            <p className="mt-5 max-w-xl text-[15px] leading-relaxed text-soft">{far.message}</p>
          </div>
        )}
        {hasFar && <Note>{far.message}</Note>}
        {far.premium_far && (
          <Panel title="Premium FAR and TDR, kept separate">
            <p className="mb-4 text-[13.5px] leading-relaxed text-soft">{far.premium_far.message}</p>
            {far.premium_far.additional_far_candidate != null && (
              <>
                <Row k="Possible additional FAR" v={`+${ratio(far.premium_far.additional_far_candidate)}`} />
                <Row k="Possible additional area" v={`+${area(far.premium_far.additional_floor_area_candidate_m2)}`} />
                <Row k="Possible total FAR" v={ratio(far.premium_far.potential_total_far_candidate)} />
                {far.premium_far.premium_only_additional_far != null && <Row k="With Premium FAR alone, no TDR" v={`+${ratio(far.premium_far.premium_only_additional_far)} · ${area(far.premium_far.premium_only_additional_area_m2)}`} />}
                {far.premium_far.charge_estimate && <Row k="Estimated Premium FAR charge" v={<span data-testid="premium-charge">₹{far.premium_far.charge_estimate.estimated_charge_inr.toLocaleString("en-IN")}</span>} />}
                {far.premium_far.charge_estimate && <p className="mt-3 text-xs leading-relaxed text-soft">{far.premium_far.charge_estimate.note}</p>}
              </>
            )}
          </Panel>
        )}
      </div>
      <div className="space-y-10">
        <Panel title="How this was found">
          <Row k="Rule profile" v={far.profile_name ?? "—"} mono={false} />
          <Row k="Rule status" v={SOURCE_STATUS_LABEL[report.application.source_status] ?? report.application.source_status} mono={false} />
          {far.category && <Row k="Category" v={far.category} mono={false} />}
          {far.table && <Row k="Table" v={far.table} mono={false} />}
          {far.selected_path && <Row k="Conditional path" v={far.selected_path} mono={false} />}
          <Row k="Plot area" v={area(report.site.site_area_m2, 2)} />
          <Row k="Road width" v={metres(report.site.road_width_m)} />
          {details.plot_area_far_cap != null && <Row k="Plot-area cap" v={ratio(details.plot_area_far_cap as number)} />}
          {details.road_width_far != null && <Row k="Road-width FAR" v={ratio(details.road_width_far as number)} />}
          {bands.map((b, i) => <Row key={i} k={`Matched band ${i + 1}`} v={`${band(b)} → ${ratio(b.far as number)}`} />)}
          {details.deduction_pct != null && <Row k="Deducted" v={`${details.deduction_pct as number}% (${details.deduction_source === "configured_rule" ? "rule" : "your assumption"})`} />}
          {far.coverage?.coverage_pct != null && <Row k="Ground coverage limit" v={`${far.coverage.coverage_pct}%`} />}
        </Panel>
        {report.road_widening && (
          <Panel title="Road widening">
            <Row k="Land taken" v={area(report.road_widening.area_taken_m2)} />
            {report.road_widening.capacity_if_land_excluded_m2 != null && <Row k="Capacity if that land is not counted" v={<span data-testid="widening-capacity">{area(report.road_widening.capacity_if_land_excluded_m2)}</span>} />}
            <p className="mt-3 text-xs leading-relaxed text-soft">Confirm with the authority whether surrendered land still counts towards FAR. Any TDR is not calculated.</p>
          </Panel>
        )}
        {far.source && (
          <Panel title="Source">
            <p className="display text-xl leading-snug">{far.source.title}</p>
            <p className="mt-2 text-[13px] leading-relaxed text-soft">{[far.source.notification, far.source.clause, far.source.document_page].filter(Boolean).join(" · ")}</p>
            {far.source.status && <p className="mt-2 text-xs leading-relaxed text-soft">{far.source.status}</p>}
            {far.source.url && <a href={far.source.url} target="_blank" rel="noreferrer noopener" className="mt-3 inline-block text-[13px] underline underline-offset-4">Open source</a>}
          </Panel>
        )}
        {!!far.conditions?.length && <Panel title="Conditions in the source"><ul className="space-y-2 text-[13px] leading-relaxed text-soft">{far.conditions.map((c) => <li key={c}>{c}</li>)}</ul></Panel>}
      </div>
    </div>
  );
}
