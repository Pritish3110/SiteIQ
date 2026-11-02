import { useEffect, useRef, useState } from "react";
import { Button, Note, Panel } from "../components/ui";
import { api } from "../lib/api";
import { SOURCE_STATUS_LABEL } from "../lib/format";
import type { Meta } from "../lib/types";

function LayerUpload({ layer, title, description }: { layer: "authority" | "zone"; title: string; description: string }) {
  const [installed, setInstalled] = useState<boolean | null>(null);
  const [message, setMessage] = useState<{ text: string; strong: boolean } | null>(null);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { api.layers().then((l) => setInstalled(l[layer])).catch(() => setInstalled(null)); }, [layer]);
  async function upload(file: File) {
    try {
      const result = await api.installLayer(layer, file);
      setInstalled(true);
      setMessage({ text: `Installed ${result.valid_polygon_count} polygons from ${result.feature_count} features.`, strong: false });
    } catch (e) { setMessage({ text: (e as Error).message, strong: true }); }
  }
  return (
    <div>
      <p className="display text-2xl">{title}</p>
      <p className="mt-1 text-[13px] leading-relaxed text-soft">{description}</p>
      <p className="mono-label mt-3">{installed === null ? "Status unknown" : installed ? "Installed" : "Not installed"}</p>
      <Button variant="line" className="mt-3" onClick={() => input.current?.click()}>Install GeoJSON</Button>
      <input ref={input} type="file" accept=".geojson,.json" aria-label={`${title} GeoJSON file`} className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; if (f) void upload(f); e.target.value = ""; }} />
      {message && <div className="mt-3"><Note tone={message.strong ? "strong" : "plain"}>{message.text}</Note></div>}
    </div>
  );
}

export function LibraryStep({ meta }: { meta: Meta }) {
  const withRules = meta.authorities.filter((a) => a.has_rules);
  const sorted = [...meta.authorities].sort((a, b) => Number(b.has_rules) - Number(a.has_rules));
  return (
    <div className="space-y-14">
      <div className="grid gap-8 sm:grid-cols-3">
        <div><p className="display text-7xl leading-none" data-testid="library-count">{withRules.length}</p><p className="mono-label mt-2">Of {meta.authorities.length} authorities have rules</p></div>
        <div><p className="display text-7xl leading-none">{meta.authorities.filter((a) => a.source_status === "verified_operative").length}</p><p className="mono-label mt-2">Verified by review</p></div>
        <p className="self-end text-[13.5px] leading-relaxed text-soft">Results stay provisional until a profile is verified by review. An authority without rules gives no FAR, and never borrows another authority's.</p>
      </div>
      <Panel title="Coverage" aside={<a href="/api/coverage.csv" className="text-[13px] underline underline-offset-4">Download CSV</a>}>
        <div className="overflow-x-auto scroll-quiet">
          <table className="w-full min-w-[640px] text-left text-[13px]" data-testid="library-table">
            <thead><tr className="border-b border-rule"><th scope="col" className="mono-label pb-2 font-normal">Authority</th><th scope="col" className="mono-label pb-2 font-normal">Can calculate FAR</th><th scope="col" className="mono-label pb-2 font-normal">Source status</th></tr></thead>
            <tbody>{sorted.map((a) => (
              <tr key={a.key} className="border-b border-rule"><th scope="row" className="py-2.5 pr-6 font-normal">{a.name}</th><td className="pr-6 font-mono text-xs">{!a.has_rules ? "No" : a.source_status === "verified_operative" ? "Yes, verified" : "Yes, provisional"}</td><td className="text-soft">{SOURCE_STATUS_LABEL[a.source_status] ?? a.source_status}</td></tr>
            ))}</tbody>
          </table>
        </div>
      </Panel>
      <details className="group border-t border-ink pt-3" data-testid="admin-tools">
        <summary className="mono-label cursor-pointer list-none !text-ink"><span className="inline-block transition-transform group-open:rotate-90">›</span> Administrator tools: official map layers</summary>
        <div className="mt-5">
        <p className="mb-6 max-w-2xl text-[13.5px] leading-relaxed text-soft">Install official layers as WGS84 GeoJSON. Each authority feature needs an <code className="font-mono text-xs">authority_key</code> property. Use notified planning boundaries, not wards or corporations, which are different things.</p>
        <div className="grid gap-10 md:grid-cols-2">
          <LayerUpload layer="authority" title="Planning boundaries" description="Lets SiteIQ test the whole plot against notified limits, and flag plots that straddle two authorities." />
          <LayerUpload layer="zone" title="Land-use zones" description="Lets SiteIQ read the official zone at the plot, instead of relying on your confirmation." />
        </div>
        </div>
      </details>
    </div>
  );
}
