import { AnimatePresence, motion } from "motion/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { RevisionPanel } from "./components/RevisionPanel";
import { Hero } from "./components/Hero";
import { StatusMark } from "./components/StatusMark";
import { Button, CountUp } from "./components/ui";
import { api } from "./lib/api";
import { area, SOURCE_STATUS_LABEL, VERDICT_LABEL } from "./lib/format";
import { deleteProject, downloadProject, listProjects, loadProject, newProjectId, parseProjectFile, saveProject, type ProjectSummary, type Revision } from "./lib/projects";
import { effectiveArea, emptyStudy, missing as missingInputs, nandiSample, toPayload, type Study } from "./lib/study";
import type { AuthorityDetail, CheckStatus, Meta, Report } from "./lib/types";
import { BoundaryStep } from "./steps/Boundary";
import { ControlsStep } from "./steps/Controls";
import { DossierStep } from "./steps/Dossier";
import { FarStep } from "./steps/Far";
import { LibraryStep } from "./steps/Library";
import { OptionsStep } from "./steps/Options";
import { SiteStep } from "./steps/Site";

const SHEETS = [
  { code: "A-01", title: "Site", heading: "Where is the site?", lead: "Identify the location and the likely planning authority." },
  { code: "A-02", title: "Boundary", heading: "Plot boundary", lead: "Bring in the survey, check it, and mark which edges face a road." },
  { code: "A-03", title: "Controls", heading: "Planning controls", lead: "Record the land use, road and constraints the rules depend on." },
  { code: "A-04", title: "FAR", heading: "Maximum FAR", lead: "The figure, exactly how it was found, and where it comes from." },
  { code: "A-05", title: "Options", heading: "Design options", lead: "Compare heights, floors, stilts and basements on the real plot." },
  { code: "A-06", title: "Dossier", heading: "Feasibility dossier", lead: "The result, everything still open, and the documents to issue." },
  { code: "L-01", title: "Rule library", heading: "Rule library", lead: "What SiteIQ can and cannot calculate, authority by authority." },
] as const;
const readStorage = (key: string) => { try { return localStorage.getItem(key); } catch { return null; } };
const writeStorage = (key: string, value: string) => { try { localStorage.setItem(key, value); } catch { /* A private window can block storage; the study still works. */ } };

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);
  const [entered, setEntered] = useState(false);
  const [study, setStudy] = useState<Study>(emptyStudy);
  const [sheet, setSheet] = useState(0);
  const [detail, setDetail] = useState<AuthorityDetail | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [assessedFor, setAssessedFor] = useState("");
  const [assessError, setAssessError] = useState<string | null>(null);
  const [theme, setTheme] = useState<"light" | "dark">(() => (readStorage("siteiq.theme") === "dark" ? "dark" : "light"));
  const [projectId, setProjectId] = useState(newProjectId);
  const [revisions, setRevisions] = useState<Revision[]>([]);
  const [recent, setRecent] = useState<ProjectSummary[]>(listProjects);
  const [openError, setOpenError] = useState<string | null>(null);
  const main = useRef<HTMLElement>(null);

  useEffect(() => { document.documentElement.dataset.theme = theme; writeStorage("siteiq.theme", theme); }, [theme]);
  useEffect(() => { api.meta().then(setMeta).catch((e) => setBootError(e.message)); }, []);
  useEffect(() => { if (entered) saveProject(projectId, study, revisions); }, [study, revisions, entered, projectId]);
  useEffect(() => { main.current?.scrollTo({ top: 0 }); }, [sheet]);
  useEffect(() => {
    if (!study.authorityKey) { setDetail(null); return; }
    let live = true;
    api.authority(study.authorityKey).then((d) => { if (live) setDetail(d); }).catch(() => { if (live) setDetail(null); });
    return () => { live = false; };
  }, [study.authorityKey]);

  const set = useCallback((patch: Partial<Study>) => setStudy((s) => ({ ...s, ...patch })), []);
  const hasRules = detail?.has_rules ?? true;
  const gaps = useMemo(() => missingInputs(study, hasRules), [study, hasRules]);
  const payload = useMemo(() => toPayload(study), [study]);
  const signature = useMemo(() => JSON.stringify(payload), [payload]);
  const ready = gaps.length === 0;

  // Live assessment: results always follow the inputs, so there is no "run" step to forget.
  useEffect(() => {
    if (!ready) { setReport(null); setAssessedFor(""); setAssessError(null); return; }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api.assess(payload, controller.signal).then((r) => { setReport(r); setAssessedFor(signature); setAssessError(null); }).catch((e) => {
        if (e.name === "AbortError") return;
        setAssessError(e.message); setReport(null); setAssessedFor("");
      });
    }, 300);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [signature, ready]); // eslint-disable-line react-hooks/exhaustive-deps
  const stale = ready && assessedFor !== signature;

  const identifyFromBoundary = useCallback(async (lonLat: [number, number]) => {
    set({ location: null, authorityConfirmed: false });
    try {
      const result = await api.identify({ boundary_point_lonlat: lonLat, proposed_use: study.proposedUse });
      setStudy((s) => {
        const key = result.suggested_authority_key;
        const known = key && meta?.authorities.some((a) => a.key === key);
        return { ...s, location: result, coordinates: result.coordinates.text, authorityKey: known ? key! : "", category: known && key === s.authorityKey ? s.category : "" };
      });
    } catch { /* The site step explains how to retry; a failed lookup leaves no stale result. */ }
  }, [meta, set, study.proposedUse]);

  if (bootError) return <div className="flex min-h-full items-center justify-center p-10"><div className="max-w-md"><p className="display text-4xl">SiteIQ could not start.</p><p className="mt-4 text-soft">{bootError}</p></div></div>;
  if (!meta) return <div className="flex min-h-full items-center justify-center"><span className="mono-label">Loading rules…</span></div>;
  if (!entered) {
    const begin = (next: Study, nextRevisions: Revision[], id: string, startSheet: number) => { setStudy(next); setRevisions(nextRevisions); setProjectId(id); setSheet(startSheet); setOpenError(null); setEntered(true); };
    return <Hero version={meta.version} recent={recent} openError={openError}
      onStart={() => begin(emptyStudy(), [], newProjectId(), 0)}
      onSample={() => begin(nandiSample(), [], newProjectId(), 5)}
      onOpenRecent={(id) => { const project = loadProject(id); if (project) begin(project.study, project.revisions, id, 0); else { setOpenError("That project could not be read on this computer."); setRecent(listProjects()); } }}
      onDeleteRecent={(id) => { deleteProject(id); setRecent(listProjects()); }}
      onOpenFile={async (file) => { try { const project = parseProjectFile(await file.text()); begin(project.study, project.revisions, newProjectId(), 0); } catch (e) { setOpenError((e as Error).message); } }} />;
  }

  const current = SHEETS[sheet];
  const sheetDone = [!!study.location || !!study.boundary, !!study.boundary, !!study.authorityKey && !!study.category && !!study.roadWidth, report?.maximum_far != null, !!report && report.scenarios.some((s) => s.gross_concept_area_m2 != null), false, false];

  return (
    <div className="grid h-full grid-rows-[auto_minmax(0,1fr)] lg:grid-cols-[13.5rem_minmax(0,1fr)_17.5rem] lg:grid-rows-1">
      <nav aria-label="Sheets" className="no-print flex items-center gap-4 overflow-x-auto border-b border-rule bg-sheet px-4 lg:flex-col lg:items-stretch lg:gap-0 lg:overflow-visible lg:border-b-0 lg:border-r lg:p-0">
        <button type="button" onClick={() => { setRecent(listProjects()); setEntered(false); }} className="display shrink-0 py-3 text-left text-[26px] leading-none lg:px-6 lg:pb-7 lg:pt-6">SiteIQ</button>
        <ol className="flex lg:flex-1 lg:flex-col">
          {SHEETS.map((s, i) => (
            <li key={s.code}>
              <button type="button" data-testid={`sheet-${i}`} aria-current={i === sheet ? "page" : undefined} onClick={() => setSheet(i)} className={`relative flex w-full items-baseline gap-3 whitespace-nowrap px-3 py-3 text-left transition-colors lg:px-6 ${i === sheet ? "text-ink" : "text-soft hover:text-ink"}`}>
                {i === sheet && <motion.span layoutId="sheet-marker" className="absolute bottom-0 left-0 right-0 h-0.5 bg-ink lg:bottom-auto lg:right-auto lg:top-0 lg:h-full lg:w-0.5" transition={{ duration: 0.35 }} />}
                <span className="font-mono text-[10.5px] tracking-wider">{s.code}</span>
                <span className={`text-sm ${i === sheet ? "font-medium" : ""}`}>{s.title}</span>
                {sheetDone[i] && <span aria-label="has content" className="ml-auto hidden size-1.5 rounded-full bg-current lg:block" />}
              </button>
            </li>
          ))}
        </ol>
        <div className="hidden border-t border-rule p-6 lg:block">
          <button type="button" data-testid="theme-toggle" onClick={() => setTheme(theme === "light" ? "dark" : "light")} className="mono-label hover:text-ink">{theme === "light" ? "Dark sheet" : "Light sheet"}</button>
        </div>
      </nav>

      <main ref={main} className="scroll-quiet relative min-w-0 overflow-y-auto">
        <div data-testid="compact-status" className="no-print sticky top-0 z-10 flex items-center justify-between gap-4 border-b border-rule bg-sheet px-6 py-2 lg:hidden">
          <span className="min-w-0 truncate text-[13px]">{study.projectName || "Untitled site"}</span>
          <span className="flex shrink-0 items-baseline gap-4 font-mono text-[11px]">
            <span>FAR {report?.maximum_far != null ? report.maximum_far.toFixed(2) : "—"}</span>
            <span>{report ? VERDICT_LABEL[report.verdict.code] : gaps.length ? `Needs ${gaps[0]}` : "Calculating"}</span>
            <button type="button" data-testid="theme-toggle-compact" onClick={() => setTheme(theme === "light" ? "dark" : "light")} className="underline underline-offset-2">{theme === "light" ? "Dark" : "Light"}</button>
          </span>
        </div>
        <div className="mx-auto max-w-[1280px] px-6 pb-20 pt-9 lg:px-12">
          <AnimatePresence mode="wait">
            <motion.div key={sheet} initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.32 }}>
              <header className="mb-11 flex items-end justify-between gap-6">
                <div>
                  <p className="mono-label mb-2">Sheet {current.code}</p>
                  <h1 className="display text-[clamp(2.6rem,4.6vw,4.25rem)] leading-none" data-testid="sheet-heading">{current.heading}</h1>
                  <p className="mt-3 text-[15px] text-soft">{current.lead}</p>
                </div>
                <div className="no-print shrink-0"><Button variant="line" data-testid="save-project" onClick={() => downloadProject(study, revisions)}>Save project file</Button></div>
              </header>
              {assessError && <div className="mb-8 border border-ink p-4 text-[13px] font-medium" role="alert" data-testid="assess-error">The assessment could not run: {assessError}</div>}
              {sheet === 0 && <SiteStep study={study} set={set} meta={meta} />}
              {sheet === 1 && <BoundaryStep study={study} set={set} onIdentify={identifyFromBoundary} />}
              {sheet === 2 && <ControlsStep study={study} set={set} meta={meta} detail={detail} />}
              {sheet === 3 && <FarStep report={report} missing={gaps} />}
              {sheet === 4 && <OptionsStep study={study} set={set} report={report} />}
              {sheet === 5 && <DossierStep study={study} report={report} payload={payload} stale={stale} missing={gaps} revisionPanel={report && <RevisionPanel study={study} report={report} payload={payload} revisions={revisions} onChange={setRevisions} onRestore={setStudy} stale={stale} />} />}
              {sheet === 6 && <LibraryStep meta={meta} />}
              <footer className="no-print mt-16 flex items-center justify-between border-t border-rule pt-5">
                <Button variant="quiet" className="!px-0" disabled={sheet === 0} onClick={() => setSheet(sheet - 1)}>← {sheet > 0 ? SHEETS[sheet - 1].title : ""}</Button>
                {sheet < SHEETS.length - 1 && <Button variant="line" data-testid="next-sheet" onClick={() => setSheet(sheet + 1)}>Next: {SHEETS[sheet + 1].title} →</Button>}
              </footer>
            </motion.div>
          </AnimatePresence>
        </div>
      </main>

      <aside aria-label="Title block" className="no-print scroll-quiet hidden flex-col overflow-y-auto border-l border-rule bg-sheet lg:flex">
        <div className="border-b border-rule p-5">
          <p className="mono-label">Project</p>
          <p className="display mt-1 break-words text-2xl leading-tight" data-testid="tb-project">{study.projectName || "Untitled site"}</p>
          {study.client && <p className="mt-1 text-xs text-soft">{study.client}</p>}
        </div>
        <div className="border-b border-rule p-5">
          <p className="mono-label">Base FAR</p>
          <p className="display mt-1 text-[4.25rem] leading-none" data-testid="tb-far">{report?.maximum_far != null ? <CountUp value={report.maximum_far} digits={2} /> : <span className="text-faint">—</span>}</p>
          <p className="mt-2 font-mono text-xs tnum">{report?.maximum_far_area_m2 != null ? `${area(report.maximum_far_area_m2)} capacity` : gaps.length ? `Needs ${gaps[0]}` : "No rule matched"}</p>
        </div>
        <dl className="space-y-3 border-b border-rule p-5 text-[12.5px]">
          <div><dt className="mono-label">Authority</dt><dd className="mt-0.5 leading-snug">{detail?.name ?? "Not chosen"}</dd></div>
          <div><dt className="mono-label">Rule status</dt><dd className="mt-0.5 leading-snug">{detail ? SOURCE_STATUS_LABEL[detail.source_status] ?? detail.source_status : "—"}</dd></div>
          <div className="grid grid-cols-2 gap-3">
            <div><dt className="mono-label">Plot</dt><dd className="mt-0.5 font-mono tnum">{area(effectiveArea(study))}</dd></div>
            <div><dt className="mono-label">Road</dt><dd className="mt-0.5 font-mono tnum">{study.roadWidth ? `${study.roadWidth} m` : "—"}</dd></div>
          </div>
        </dl>
        <div className="flex-1 p-5">
          <p className="mono-label">Status</p>
          {report ? (
            <button type="button" onClick={() => setSheet(5)} className="mt-1 block w-full text-left">
              <span className="display block text-3xl" data-testid="tb-verdict">{VERDICT_LABEL[report.verdict.code]}</span>
              <span className="mt-3 block space-y-1.5">
                {(["FAIL", "NEEDS_INPUT", "REFER", "NOT_CONFIGURED", "PASS"] as CheckStatus[]).map((s) => report.verdict.counts[s] > 0 && (
                  <span key={s} className="flex items-center justify-between font-mono text-[11px]"><span className="flex items-center gap-2"><StatusMark status={s} size={11} />{{ FAIL: "Fail", NEEDS_INPUT: "Needs input", REFER: "Confirm", NOT_CONFIGURED: "Not configured", PASS: "Pass" }[s]}</span><span className="tnum">{report.verdict.counts[s]}</span></span>
                ))}
              </span>
            </button>
          ) : <p className="mt-1 text-[13px] leading-relaxed text-soft">{gaps.length ? `Still needed: ${gaps.join(", ")}.` : "Calculating…"}</p>}
        </div>
        <div className="border-t border-rule px-5 py-3 font-mono text-[10px] leading-relaxed text-soft">
          <div className="flex justify-between"><span>SiteIQ v{meta.version}</span><span>{current.code}</span></div>
          <div>Preliminary. Not for sanction.{stale ? " · Recalculating" : ""}</div>
        </div>
      </aside>
    </div>
  );
}
