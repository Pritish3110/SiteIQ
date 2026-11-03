import { motion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { PlotCanvas } from "../components/PlotCanvas";
import { Button, Check, Field, Note, Panel, Row, Segmented, Select } from "../components/ui";
import { api } from "../lib/api";
import { area, metres, positive } from "../lib/format";
import { edgeLengths } from "../lib/geometry";
import { emptyBoundaryDraft, type AppliedBoundary, type BoundaryDraft, type Study } from "../lib/study";
import type { Candidate, EdgeRole, ParsedFile } from "../lib/types";

const UNITS: Record<string, number> = { Metres: 1, Millimetres: 0.001, Centimetres: 0.01, Feet: 0.3048, Inches: 0.0254 };
const NEXT_ROLE: Record<EdgeRole, EdgeRole> = { side: "road", road: "rear", rear: "left", left: "right", right: "side" };

export function BoundaryStep({ study, set, onIdentify, draft, setDraft }: { study: Study; set: (p: Partial<Study>) => void; onIdentify: (lonLat: [number, number]) => void; draft: BoundaryDraft; setDraft: (f: (d: BoundaryDraft) => BoundaryDraft) => void }) {
  const { parsed, candidateId, unit, calibrateEdge, calibrateLength, closeOpen, validated, roles } = draft;
  const update = (patch: Partial<BoundaryDraft>) => setDraft((d) => ({ ...d, ...patch }));
  const setParsed = (v: ParsedFile | null) => update({ parsed: v });
  const setCandidateId = (v: string) => update({ candidateId: v });
  const setUnit = (v: string) => update({ unit: v });
  const setCalibrateEdge = (v: string) => update({ calibrateEdge: v });
  const setCalibrateLength = (v: string) => update({ calibrateLength: v });
  const setCloseOpen = (v: boolean) => update({ closeOpen: v });
  const setRoles = (next: Record<number, EdgeRole> | ((r: Record<number, EdgeRole>) => Record<number, EdgeRole>)) =>
    setDraft((d) => ({ ...d, roles: typeof next === "function" ? next(d.roles) : next }));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const candidate: Candidate | null = useMemo(() => parsed?.candidates.find((c) => c.candidate_id === candidateId) ?? null, [parsed, candidateId]);
  const scale = useMemo(() => {
    if (!candidate) return null;
    if (candidate.scale_to_m) return candidate.scale_to_m;
    if (unit) return UNITS[unit];
    const known = positive(calibrateLength);
    if (known && calibrateEdge !== "") { const raw = edgeLengths(candidate.points)[Number(calibrateEdge)]; return raw > 0 ? known / raw : null; }
    return null;
  }, [candidate, unit, calibrateEdge, calibrateLength]);

  const validationKey = `${parsed?.fingerprint ?? ""}|${candidateId}|${scale ?? ""}|${closeOpen}`;
  useEffect(() => {
    if (!candidate) { if (validated) update({ validated: null, validatedFor: "" }); return; }
    // Coming back to this sheet must not re-check the outline or clear the edges already tagged.
    if (draft.validatedFor === validationKey) return;
    let live = true;
    api.validate(candidate, scale, closeOpen).then((r) => { if (live) update({ validated: r, validatedFor: validationKey, roles: {} }); }).catch((e) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [validationKey]); // eslint-disable-line react-hooks/exhaustive-deps

  async function upload(file: File) {
    setBusy(true); setError(null); setDraft(() => emptyBoundaryDraft());
    try {
      const result = await api.parse(file);
      setParsed(result);
      if (!result.candidates.length) setError("No usable boundary was found in this file. Check that it is on a closed polyline or a KML polygon.");
      else if (result.candidates.length === 1) setCandidateId(result.candidates[0].candidate_id);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  function apply() {
    if (!validated?.valid || !candidate || !parsed) return;
    const v = validated.validation;
    const next: AppliedBoundary = {
      sourceFile: parsed.filename, sourceType: candidate.source_type, sourceUnits: candidate.source_units, scale, fingerprint: parsed.fingerprint, candidateId: candidate.candidate_id,
      points: validated.points_m!, holes: validated.holes_m ?? [], area: v.area_m2!, perimeter: v.perimeter_m!, convex: !!v.is_convex, notes: v.notes ?? [], wgs84: candidate.source_points_wgs84, holesWgs84: candidate.source_holes_wgs84,
      useComputedArea: true, roles, roadWidths: {},
    };
    set({ boundary: next, overlays: Object.fromEntries(Object.entries(study.overlays).map(([k, o]) => [k, { ...o, edge: "" }])) });
    setDraft(() => emptyBoundaryDraft());
    const point = candidate.source_location_point_wgs84;
    if (point) onIdentify([point[0], point[1]]);
  }

  const applied = study.boundary;
  const cycleApplied = (i: number) => {
    if (!applied) return;
    const nextRole = NEXT_ROLE[applied.roles[i] ?? "side"];
    set({ boundary: { ...applied, roles: { ...applied.roles, [i]: nextRole } } });
  };
  const roadEdges = applied ? Object.entries(applied.roles).filter(([, r]) => r === "road").map(([i]) => Number(i)) : [];

  const previewPoints = validated?.valid ? validated.points_m! : candidate && !validated?.valid ? null : null;

  return (
    <div className="grid gap-x-14 gap-y-12 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)]">
      <div className="space-y-10">
        <Panel title="Survey file">
          <button type="button" data-testid="dropzone" onClick={() => input.current?.click()} onDragOver={(e) => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)}
            onDrop={(e) => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) void upload(f); }}
            className={`relative w-full border border-dashed px-6 py-10 text-center transition-colors ${dragging ? "border-ink bg-wash" : "border-soft hover:border-ink hover:bg-wash"}`}>
            <span className="display block text-2xl">{busy ? "Reading the file…" : "Drop a boundary file"}</span>
            <span className="mt-1 block text-[13px] text-soft">DXF, KML, KMZ or vector PDF, up to 40 MB. For DWG, save as DXF first.</span>
          </button>
          <input ref={input} data-testid="file-input" type="file" accept=".dxf,.kml,.kmz,.pdf,.dwg" className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; if (f) void upload(f); e.target.value = ""; }} />
          {error && <div className="mt-5"><Note tone="strong" testId="boundary-error">{error}</Note></div>}
          {parsed?.meta.warnings?.length ? <ul className="mt-5 space-y-2">{parsed.meta.warnings.map((w) => <li key={w}><Note>{w}</Note></li>)}</ul> : null}
        </Panel>

        {parsed && parsed.candidates.length > 0 && (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
            <Panel title={`Found in ${parsed.filename}`}>
              <Select label="Which feature is the plot?" value={candidateId} onChange={setCandidateId} testId="candidate-select" placeholder={`Choose from ${parsed.candidates.length}`}
                options={parsed.candidates.map((c) => ({ value: c.candidate_id, label: c.label, note: `${c.points.length} vertices · ${c.closed ? "closed" : "open path"}` }))} />
              {candidate && !candidate.scale_to_m && (
                <div className="mt-6 space-y-5">
                  <Note tone="strong">This drawing does not state its scale. Set it before the area can be calculated.</Note>
                  {candidate.source_type === "dxf" && <Select label="Drawing units" value={unit} onChange={(v) => { setUnit(v); setCalibrateLength(""); }} options={Object.keys(UNITS).map((u) => ({ value: u, label: u }))} testId="units-select" />}
                  <div className="grid grid-cols-2 gap-5">
                    <Select label="Or calibrate an edge" value={calibrateEdge} onChange={(v) => { setCalibrateEdge(v); setUnit(""); }} options={edgeLengths(candidate.points).slice(0, 60).map((l, i) => ({ value: String(i), label: `Edge ${i + 1}`, note: `${l.toFixed(2)} drawing units` }))} />
                    <Field label="Its surveyed length" type="number" unit="m" value={calibrateLength} onChange={(v) => { setCalibrateLength(v); setUnit(""); }} disabled={calibrateEdge === ""} />
                  </div>
                </div>
              )}
              {candidate && !candidate.closed && <div className="mt-6"><Check label="The last-to-first edge is a real plot boundary" hint="This path is open. Only join it if that edge follows the legal boundary." checked={closeOpen} onChange={setCloseOpen} testId="close-open" /></div>}
              {validated && !validated.valid && <div className="mt-6"><Note tone="strong" testId="validation-message">{validated.validation.message}</Note></div>}
              {validated?.valid && (
                <div className="mt-6">
                  <Row k="Calculated area" v={<span data-testid="preview-area">{area(validated.validation.area_m2, 2)}</span>} />
                  <Row k="Perimeter" v={metres(validated.validation.perimeter_m)} />
                  <Row k="Vertices" v={validated.validation.vertex_count} />
                  {!!validated.validation.hole_count && <Row k="Inner areas excluded" v={validated.validation.hole_count} />}
                  {validated.validation.notes?.map((n) => <div className="mt-3" key={n}><Note>{n}</Note></div>)}
                  <Button className="mt-6 w-full" onClick={apply} data-testid="apply-boundary">Use this boundary</Button>
                  <p className="mt-2 text-xs text-soft">Not in use until you press this.</p>
                </div>
              )}
            </Panel>
          </motion.div>
        )}

        {applied && !parsed && (
          <Panel title="In use">
            <Row k="Source" v={applied.sourceFile} mono={false} />
            <Row k="Area" v={<span data-testid="applied-area">{area(applied.area, 2)}</span>} />
            <Row k="Perimeter" v={metres(applied.perimeter)} />
            <Row k="Vertices" v={applied.points.length} />
            {!!applied.holes.length && <Row k="Inner areas excluded" v={applied.holes.length} />}
            {applied.notes.map((n) => <div className="mt-3" key={n}><Note>{n}</Note></div>)}
            <div className="mt-6 space-y-5">
              <Field label="Area on title or survey" type="number" unit="m²" value={study.stated} onChange={(v) => set({ stated: v })} testId="stated-area" hint="Compared with the drawn area to catch a wrong outline." />
              <Segmented label="Area for FAR" compact value={applied.useComputedArea ? "drawn" : "typed"} onChange={(v) => set({ boundary: { ...applied, useComputedArea: v === "drawn" } })} options={[{ value: "drawn", label: "Drawn boundary" }, { value: "typed", label: "Typed on next sheet" }]} />
            </div>
            <Button variant="quiet" className="mt-5 !px-0" onClick={() => set({ boundary: null })} data-testid="remove-boundary">Remove this boundary</Button>
          </Panel>
        )}
      </div>

      <div className="relative">
        <div className="relative border border-rule bg-sheet drafting-grid">
          <span className="tick -left-[6px] -top-[6px]" /><span className="tick -right-[6px] -top-[6px]" /><span className="tick -bottom-[6px] -left-[6px]" /><span className="tick -bottom-[6px] -right-[6px]" />
          {previewPoints ? (
            <PlotCanvas testId="plot-canvas" points={previewPoints} holes={validated?.holes_m} roles={roles} north={candidate?.source_type === "kml"} onEdgeClick={(i) => setRoles((r) => ({ ...r, [i]: NEXT_ROLE[r[i] ?? "side"] }))} />
          ) : applied ? (
            <PlotCanvas testId="plot-canvas" points={applied.points} holes={applied.holes} roles={applied.roles} north={applied.sourceType === "kml"} onEdgeClick={cycleApplied} />
          ) : (
            <div className="flex aspect-[76/56] items-center justify-center p-10 text-center"><p className="display max-w-sm text-3xl text-faint">The plot will be drawn here at its true shape.</p></div>
          )}
        </div>
        {(previewPoints || applied) && (
          <div className="mt-4 flex flex-wrap items-start justify-between gap-x-8 gap-y-3">
            <p className="max-w-md text-[13px] leading-relaxed text-soft"><strong className="font-medium text-ink">Click each edge</strong> to cycle through road, rear, left, right and side. An edge left as side takes the larger side setback. SiteIQ never guesses the frontage from the shape.</p>
            <div className="flex gap-5 font-mono text-[10.5px] text-soft">
              <span className="flex items-center gap-2"><svg width="26" height="6"><line x1="0" y1="3" x2="26" y2="3" stroke="currentColor" strokeWidth="3" /></svg>Road</span>
              <span className="flex items-center gap-2"><svg width="26" height="6"><line x1="0" y1="3" x2="26" y2="3" stroke="currentColor" strokeWidth="1.5" strokeDasharray="6 3" /></svg>Rear</span>
              <span className="flex items-center gap-2"><svg width="26" height="6"><line x1="0" y1="3" x2="26" y2="3" stroke="currentColor" /></svg>Side</span>
            </div>
          </div>
        )}
        {applied && roadEdges.length > 0 && (
          <Panel title="Road on each frontage" className="mt-8">
            <div className="grid gap-5 sm:grid-cols-3">{roadEdges.map((i) => <Field key={i} label={`Edge ${i + 1}`} type="number" unit="m" value={applied.roadWidths[i] ?? ""} onChange={(v) => set({ boundary: { ...applied, roadWidths: { ...applied.roadWidths, [i]: v } } })} />)}</div>
            <p className="mt-3 text-xs leading-relaxed text-soft">Different widths are flagged for review. The FAR uses the road width on the next sheet.</p>
          </Panel>
        )}
      </div>
    </div>
  );
}
