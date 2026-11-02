import { useMemo, useState } from "react";
import { diffInputs, diffSummaries, newProjectId, normaliseStudy, summariseReport, type Change, type Revision } from "../lib/projects";
import type { Study } from "../lib/study";
import type { Report } from "../lib/types";
import { Button, Field, Note, Panel, Select } from "./ui";

function Changes({ title, rows }: { title: string; rows: Change[] }) {
  return (
    <div>
      <p className="mono-label mb-2">{title}</p>
      {rows.length === 0 ? <p className="text-[13px] text-soft">No differences.</p> : (
        <table className="w-full text-left text-[13px]">
          <thead><tr className="border-b border-rule"><th scope="col" className="mono-label pb-1.5 font-normal">Item</th><th scope="col" className="mono-label pb-1.5 font-normal">Saved</th><th scope="col" className="mono-label pb-1.5 font-normal">Now</th></tr></thead>
          <tbody>{rows.map((r) => <tr key={r.label} className="border-b border-rule"><th scope="row" className="py-1.5 pr-4 font-normal">{r.label}</th><td className="pr-4 font-mono text-xs">{r.from}</td><td className="font-mono text-xs font-semibold">{r.to}</td></tr>)}</tbody>
        </table>
      )}
    </div>
  );
}

export function RevisionPanel({ study, report, payload, revisions, onChange, onRestore, stale }: { study: Study; report: Report; payload: unknown; revisions: Revision[]; onChange: (r: Revision[]) => void; onRestore: (s: Study) => void; stale: boolean }) {
  const [name, setName] = useState("");
  const [selected, setSelected] = useState("");
  const chosen = revisions.find((r) => r.id === selected) ?? revisions[revisions.length - 1];
  const inputChanges = useMemo(() => (chosen ? diffInputs(chosen.inputs, payload) : []), [chosen, payload]);
  const resultChanges = useMemo(() => (chosen ? diffSummaries(chosen.summary, summariseReport(report)) : []), [chosen, report]);

  function save() {
    const revision: Revision = { id: newProjectId(), name: name.trim() || `Revision ${revisions.length + 1}`, savedAt: new Date().toISOString(), inputs: JSON.parse(JSON.stringify(payload)), summary: summariseReport(report), study: JSON.parse(JSON.stringify(study)) };
    onChange([...revisions, revision]); setName(""); setSelected(revision.id);
  }

  return (
    <Panel title="Revisions" aside={<span className="text-xs text-soft">Saved with the project</span>}>
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        <div className="space-y-4">
          <Field label="Name this revision" value={name} onChange={setName} placeholder={`Revision ${revisions.length + 1}`} testId="revision-name" />
          <Button variant="line" disabled={stale} onClick={save} data-testid="save-revision">Save revision</Button>
          {revisions.length > 0 && <Select label="Compare with" value={chosen?.id ?? ""} onChange={setSelected} testId="revision-select" options={revisions.map((r) => ({ value: r.id, label: r.name, note: new Date(r.savedAt).toLocaleString("en-IN") }))} />}
          {chosen && <Button variant="quiet" className="!px-0" data-testid="restore-revision" onClick={() => onRestore(normaliseStudy(chosen.study))}>Restore this revision's inputs</Button>}
        </div>
        {chosen ? (
          <div className="space-y-8" data-testid="revision-diff">
            <Changes title="Results" rows={resultChanges} />
            <Changes title="Inputs" rows={inputChanges} />
          </div>
        ) : <Note>Save a revision before you change anything. You will then see exactly what moved, including after a rule update.</Note>}
      </div>
    </Panel>
  );
}
