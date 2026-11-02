import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { Button, Check, Field, Note, Panel, Row, Segmented } from "../components/ui";
import { api } from "../lib/api";
import { humanise } from "../lib/format";
import type { Study } from "../lib/study";
import type { Meta } from "../lib/types";

type Mode = "link" | "coordinates" | "address";

export function SiteStep({ study, set, meta }: { study: Study; set: (p: Partial<Study>) => void; meta: Meta }) {
  const [mode, setMode] = useState<Mode>(study.coordinates && !study.mapUrl ? "coordinates" : study.address && !study.mapUrl ? "address" : "link");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const location = study.location;
  const usingBoundary = !!study.boundary?.wgs84;

  async function identify() {
    setBusy(true); setError(null);
    // Failing closed: nothing from an earlier lookup survives a new attempt.
    set({ location: null, authorityConfirmed: false });
    try {
      const anchor = study.boundary?.wgs84 ? study.boundary.wgs84.reduce((acc, p) => [acc[0] + p[0] / study.boundary!.wgs84!.length, acc[1] + p[1] / study.boundary!.wgs84!.length], [0, 0]) : null;
      const result = await api.identify({
        map_url: mode === "link" ? study.mapUrl : "", coordinates: mode === "coordinates" ? study.coordinates : "", address: mode === "address" ? study.address : "",
        proposed_use: study.proposedUse, boundary_point_lonlat: anchor,
      });
      const key = result.suggested_authority_key;
      set({ location: result, authorityKey: key && meta.authorities.some((a) => a.key === key) ? key : "", authorityConfirmed: false, category: "", zoneConfirmed: false, coordinates: result.coordinates.text });
    } catch (e) {
      setError((e as Error).message);
      set({ location: null, authorityKey: "", category: "", authorityConfirmed: false });
    } finally { setBusy(false); }
  }

  const authorityName = meta.authorities.find((a) => a.key === study.authorityKey)?.name;
  const comparison = location?.input_coordinate_comparison;
  const precision = location?.map_link_resolution;

  return (
    <div className="grid gap-x-16 gap-y-12 xl:grid-cols-2">
      <div className="space-y-12">
        <Panel title="Project">
          <div className="grid gap-6 sm:grid-cols-2">
            <Field label="Project name" value={study.projectName} onChange={(v) => set({ projectName: v })} placeholder="Name this study" testId="project-name" />
            <Field label="Client or job code" value={study.client} onChange={(v) => set({ client: v })} placeholder="Optional" />
          </div>
        </Panel>
        <Panel title="Where is the site?">
          {usingBoundary ? (
            <Note>The applied boundary locates this site, and takes priority over anything typed here.</Note>
          ) : (
            <div className="space-y-6">
              <Segmented value={mode} onChange={setMode} testId="location-mode" options={[{ value: "link", label: "Google Maps link" }, { value: "coordinates", label: "Coordinates" }, { value: "address", label: "Address" }]} />
              <AnimatePresence mode="wait">
                <motion.div key={mode} initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -8 }} transition={{ duration: 0.2 }}>
                  {mode === "link" && <Field label="Map link" value={study.mapUrl} onChange={(v) => set({ mapUrl: v })} placeholder="https://maps.app.goo.gl/…" testId="map-url" hint="A link with a dropped pin is the most exact." />}
                  {mode === "coordinates" && <Field label="Latitude, longitude" value={study.coordinates} onChange={(v) => set({ coordinates: v })} placeholder="13.0735, 77.7824" testId="coordinates" hint="Decimal degrees, or degrees, minutes and seconds." />}
                  {mode === "address" && <Field label="Address or locality" value={study.address} onChange={(v) => set({ address: v })} placeholder="Village, taluk, district" testId="address" hint="Least exact. It is sent to OpenStreetMap and is only a guide to the location." />}
                </motion.div>
              </AnimatePresence>
            </div>
          )}
          <div className="mt-7">
            <Button onClick={identify} disabled={busy || (!usingBoundary && !(mode === "link" ? study.mapUrl : mode === "coordinates" ? study.coordinates : study.address).trim())} data-testid="identify">
              {busy ? "Looking up…" : "Find location and authority"}
            </Button>
          </div>
          {error && <div className="mt-6"><Note tone="strong" testId="location-error">{error} Earlier location results were cleared.</Note></div>}
        </Panel>
      </div>

      <Panel title="What the lookup found">
        {!location ? <p className="max-w-md text-[15px] leading-relaxed text-soft">Nothing yet. SiteIQ will show the exact point it used and where that came from, before any rule is applied.</p> : (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-7">
            <div>
              <p className="mono-label mb-2">Likely planning authority</p>
              <p className="display text-4xl leading-tight" data-testid="found-authority">{authorityName ?? "Not identified"}</p>
              <p className="mt-3 max-w-xl text-[13.5px] leading-relaxed text-soft">{location.authority?.reason}</p>
            </div>
            <div>
              <Row k="Point used" v={<span data-testid="found-coordinates">{location.coordinates.text}</span>} />
              <Row k="Taken from" v={location.location_source} mono={false} />
              {location.geocoded_address && <Row k="Nearest address" v={location.geocoded_address} mono={false} />}
              <Row k="Evidence" v={location.authority?.status === "matched_polygon_layer" ? "Installed boundary layer" : "Place name only"} mono={false} />
              <Row k="Official land use" v={location.zone?.value ?? "Not verified"} mono={false} />
            </div>
            {comparison?.mismatch && <Note tone="strong">The map pin is {comparison.distance_km.toFixed(1)} km from the coordinates you typed. The map link was used. Check which is right.</Note>}
            {precision?.warning && <Note tone="strong">{precision.warning}</Note>}
            {location.authority?.status !== "matched_polygon_layer" && <Note>A place name does not prove the plot is inside a notified planning area. Check the official map, then confirm below.</Note>}
            {study.authorityKey && <Check label="I have checked this authority against the official planning-area map" checked={study.authorityConfirmed} onChange={(v) => set({ authorityConfirmed: v })} testId="confirm-authority" />}
            {!!location.public_sources?.length && (
              <div>
                <p className="mono-label mb-2">Official sources to check</p>
                <ul className="space-y-1.5">{location.public_sources.slice(0, 5).map((s) => <li key={s.url}><a href={s.url} target="_blank" rel="noreferrer noopener" className="text-[13px] underline decoration-rule underline-offset-4 hover:decoration-ink">{s.title ?? humanise(s.url)}</a></li>)}</ul>
              </div>
            )}
          </motion.div>
        )}
      </Panel>
    </div>
  );
}
