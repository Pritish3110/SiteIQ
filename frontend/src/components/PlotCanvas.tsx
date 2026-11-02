import { AnimatePresence, motion } from "motion/react";
import { useId, useMemo } from "react";
import { edgeLengths, niceLength } from "../lib/geometry";
import type { EdgeRole, Envelope, Geometry, Point } from "../lib/types";

const rings = (g?: Geometry | null): Point[][] => {
  if (!g) return [];
  if (g.type === "Polygon") return g.coordinates as Point[][];
  return (g.coordinates as Point[][][]).flat();
};

export function PlotCanvas({ points, holes = [], roles = {}, onEdgeClick, envelope, basement, north, compact, selectedEdge, testId, label }: {
  points: Point[]; holes?: Point[][]; roles?: Record<number, EdgeRole>; onEdgeClick?: (index: number) => void; envelope?: Envelope | null; basement?: Envelope | null; north?: boolean; compact?: boolean; selectedEdge?: number | null; testId?: string; label?: string;
}) {
  const id = useId().replace(/:/g, "");
  const view = useMemo(() => {
    const xs = points.map((p) => p[0]); const ys = points.map((p) => p[1]);
    const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
    const w = Math.max(maxX - minX, 1), h = Math.max(maxY - minY, 1);
    const canvasW = compact ? 400 : 760, canvasH = compact ? 300 : 560, pad = compact ? 26 : 74;
    const scale = Math.min((canvasW - pad * 2) / w, (canvasH - pad * 2) / h);
    const ox = (canvasW - w * scale) / 2, oy = (canvasH - h * scale) / 2;
    return { canvasW, canvasH, scale, fx: (x: number) => ox + (x - minX) * scale, fy: (y: number) => canvasH - oy - (y - minY) * scale };
  }, [points, compact]);
  const { fx, fy, scale, canvasW, canvasH } = view;
  const path = (ring: Point[]) => ring.map(([x, y], i) => `${i ? "L" : "M"}${fx(x).toFixed(1)} ${fy(y).toFixed(1)}`).join(" ") + "Z";
  const lengths = edgeLengths(points);
  const parcelPath = path(points) + holes.map(path).join("");
  const envRings = rings(envelope?.geometry);
  const baseRings = rings(basement?.geometry);
  const barMetres = niceLength((canvasW * 0.16) / scale);
  const showEdgeLabels = !compact && points.length <= 40;
  const cx = points.reduce((s, p) => s + fx(p[0]), 0) / points.length, cy = points.reduce((s, p) => s + fy(p[1]), 0) / points.length;

  return (
    <svg data-testid={testId} viewBox={`0 0 ${canvasW} ${canvasH}`} role="img" aria-label={label ?? `Plot boundary with ${points.length} edges`} className="block h-auto w-full select-none">
      <defs>
        <pattern id={`${id}-hatch`} width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="7" stroke="var(--ink)" strokeWidth=".6" opacity=".38" /></pattern>
        <mask id={`${id}-zone`}><path d={parcelPath} fill="white" fillRule="evenodd" />{envRings.length > 0 && <path d={envRings.map(path).join("")} fill="black" fillRule="evenodd" />}</mask>
      </defs>
      {envRings.length > 0 && <rect width={canvasW} height={canvasH} fill={`url(#${id}-hatch)`} mask={`url(#${id}-zone)`} />}
      {holes.map((h, i) => <path key={i} d={path(h)} fill="var(--ink)" opacity=".12" />)}
      <AnimatePresence mode="popLayout">
        {envRings.length > 0 && <motion.path key={envRings.map(path).join("")} data-testid="envelope-line" d={envRings.map(path).join("")} fill="var(--sheet)" fillRule="evenodd" stroke="var(--ink)" strokeWidth="1.2" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.4 }} />}
        {baseRings.length > 0 && <motion.path key={"b" + baseRings.map(path).join("")} d={baseRings.map(path).join("")} fill="none" stroke="var(--ink)" strokeWidth=".9" strokeDasharray="6 3 1 3" initial={{ opacity: 0 }} animate={{ opacity: 0.8 }} exit={{ opacity: 0 }} />}
      </AnimatePresence>
      {points.map(([x, y], i) => {
        const [nx, ny] = points[(i + 1) % points.length];
        const x1 = fx(x), y1 = fy(y), x2 = fx(nx), y2 = fy(ny);
        const role = roles[i] ?? "side";
        const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
        const dx = x2 - x1, dy = y2 - y1, len = Math.hypot(dx, dy) || 1;
        let ux = -dy / len, uy = dx / len;
        if ((mx + ux - cx) ** 2 + (my + uy - cy) ** 2 < (mx - cx) ** 2 + (my - cy) ** 2) { ux = -ux; uy = -uy; }
        let angle = (Math.atan2(dy, dx) * 180) / Math.PI;
        if (angle > 90 || angle < -90) angle += 180;
        const offset = 19;
        const text = `${role === "road" ? "ROAD · " : role === "rear" ? "REAR · " : ""}E${i + 1} · ${lengths[i].toFixed(2)} m`;
        const interactive = !!onEdgeClick;
        return (
          <g key={i} data-testid={`edge-${i}`} data-role={role} onClick={interactive ? () => onEdgeClick!(i) : undefined} onKeyDown={interactive ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onEdgeClick!(i); } } : undefined}
            tabIndex={interactive ? 0 : undefined} role={interactive ? "button" : undefined} aria-label={interactive ? `Edge ${i + 1}, ${lengths[i].toFixed(2)} metres, ${role}. Press to change.` : undefined} className={interactive ? "group cursor-pointer outline-none" : ""}>
            {interactive && <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="transparent" strokeWidth="22" />}
            {interactive && <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--ink)" strokeWidth="9" opacity={selectedEdge === i ? 0.22 : 0} className="transition-opacity duration-200 group-hover:opacity-15 group-focus-visible:opacity-30" />}
            <motion.line x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--ink)" initial={{ pathLength: 0 }} animate={{ pathLength: 1, strokeWidth: role === "road" ? 3.4 : role === "rear" ? 1.6 : 1.3 }} transition={{ duration: 0.8, delay: compact ? 0 : i * 0.05 }} strokeDasharray={role === "rear" ? "9 4" : undefined} />
            {role === "road" && !compact && <line x1={x1 + ux * 8} y1={y1 + uy * 8} x2={x2 + ux * 8} y2={y2 + uy * 8} stroke="var(--ink)" strokeWidth=".7" />}
            {showEdgeLabels && (
              <text transform={`translate(${mx + ux * offset * (role === "road" ? 1.45 : 1)} ${my + uy * offset * (role === "road" ? 1.45 : 1)}) rotate(${angle})`} textAnchor="middle" dominantBaseline="middle" fontFamily="var(--font-mono)" fontSize={points.length > 16 ? 9 : 12} fontWeight={role === "road" ? 600 : 400} fill="var(--ink)">{text}</text>
            )}
          </g>
        );
      })}
      {!compact && points.map(([x, y], i) => <rect key={i} x={fx(x) - 2} y={fy(y) - 2} width="4" height="4" fill="var(--sheet)" stroke="var(--ink)" strokeWidth=".8" pointerEvents="none" />)}
      <g transform={`translate(${compact ? 14 : 28} ${canvasH - (compact ? 14 : 28)})`} fontFamily="var(--font-mono)" fontSize={compact ? 11 : 11} fill="var(--ink)">
        <line x1="0" y1="0" x2={barMetres * scale} y2="0" stroke="var(--ink)" strokeWidth="1.5" /><line x1="0" y1="-4" x2="0" y2="4" stroke="var(--ink)" /><line x1={barMetres * scale} y1="-4" x2={barMetres * scale} y2="4" stroke="var(--ink)" />
        <text x={barMetres * scale + 6} y="3">{barMetres} m</text>
      </g>
      {north && !compact && <g transform={`translate(${canvasW - 44} 46)`} fill="var(--ink)"><circle r="15" fill="none" stroke="var(--ink)" strokeWidth=".8" /><path d="M0 -13 5 9 0 5 -5 9Z" /><text y="-20" textAnchor="middle" fontFamily="var(--font-mono)" fontSize="9">N</text></g>}
    </svg>
  );
}
