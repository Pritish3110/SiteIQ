import { motion } from "motion/react";
import { Button } from "./ui";

const PLOT = "M150 370 L520 410 L600 150 L330 70 L120 130 Z";
const ENVELOPE = "M185 335 L490 368 L550 178 L335 110 L164 158 Z";
const draw = (delay: number, duration = 1.6) => ({ initial: { pathLength: 0 }, animate: { pathLength: 1 }, transition: { duration, delay, ease: [0.65, 0, 0.35, 1] as const } });

export function Hero({ version, onStart, onSample, hasDraft, onResume }: { version: string; onStart: () => void; onSample: () => void; hasDraft: boolean; onResume: () => void }) {
  return (
    <div className="relative flex min-h-full flex-col overflow-hidden bg-sheet">
      <div className="drafting-grid absolute inset-0" aria-hidden />
      <header className="relative flex items-center justify-between border-b border-rule px-8 py-5">
        <span className="display text-2xl">SiteIQ</span>
        <span className="mono-label">Site feasibility · Karnataka · v{version}</span>
      </header>
      <main className="relative grid flex-1 items-center gap-10 px-8 py-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] lg:px-16">
        <div>
          <motion.p initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="mono-label mb-6">For architects · Early-stage studies</motion.p>
          <motion.h1 initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08, duration: 0.9 }} className="display text-[clamp(3.25rem,6.6vw,6.75rem)] leading-[0.96]">
            What can this<br />plot <em>actually</em><br />carry?
          </motion.h1>
          <motion.p initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }} className="mt-8 max-w-[34rem] text-[17px] leading-relaxed text-soft">
            Start from the survey boundary. SiteIQ finds the rule, draws the envelope, compares your options and tells you plainly what it could not confirm.
          </motion.p>
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }} className="mt-10 flex flex-wrap items-center gap-3">
            <Button onClick={onStart} data-testid="start-study" className="!px-6 !py-3.5 !text-sm">Start a new study</Button>
            {hasDraft && <Button variant="line" onClick={onResume} data-testid="resume-study" className="!px-6 !py-3.5 !text-sm">Resume your draft</Button>}
            <Button variant="quiet" onClick={onSample} data-testid="load-sample">Open the sample study →</Button>
          </motion.div>
        </div>
        <div className="relative" aria-hidden>
          <svg viewBox="0 0 720 500" className="w-full">
            <defs>
              <pattern id="hero-hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="8" stroke="var(--ink)" strokeWidth=".6" opacity=".4" /></pattern>
              <mask id="hero-zone"><path d={PLOT} fill="white" /><path d={ENVELOPE} fill="black" /></mask>
            </defs>
            <motion.rect width="720" height="500" fill="url(#hero-hatch)" mask="url(#hero-zone)" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.8, duration: 0.8 }} />
            <motion.path d={PLOT} fill="none" stroke="var(--ink)" strokeWidth="2.2" {...draw(0.2)} />
            <motion.path d={ENVELOPE} fill="var(--sheet)" fillOpacity="0" stroke="var(--ink)" strokeWidth="1" {...draw(1.3, 1.2)} />
            <motion.path d="M150 392 L520 432" stroke="var(--ink)" strokeWidth=".8" fill="none" {...draw(2.1, 0.6)} />
            <motion.g fontFamily="var(--font-mono)" fontSize="10.5" fill="var(--ink)" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 2.4 }}>
              <text x="310" y="442" transform="rotate(6 310 442)">ROAD · 18.50 m WIDE</text>
              <text x="620" y="290" transform="rotate(-72 620 290)">E2 · 68.20 m</text>
              <text x="345" y="200" textAnchor="middle" fontSize="11">BUILDABLE ENVELOPE</text>
            </motion.g>
            <motion.g initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 2.6 }}>
              <text x="345" y="290" textAnchor="middle" fontFamily="var(--font-serif)" fontSize="62" fill="var(--ink)">2.50</text>
              <text x="345" y="312" textAnchor="middle" fontFamily="var(--font-mono)" fontSize="9.5" letterSpacing="1.2" fill="var(--soft)">FAR · ILLUSTRATIVE</text>
            </motion.g>
          </svg>
        </div>
      </main>
      <footer className="relative flex flex-wrap justify-between gap-3 border-t border-rule px-8 py-4 text-xs text-soft">
        <span>A preliminary feasibility aid. Not sanction advice or a legal opinion.</span>
        <span>Runs on this computer. Location lookups contact Google Maps and OpenStreetMap.</span>
      </footer>
    </div>
  );
}
