import type { Point } from "./types";

export const shoelace = (pts: Point[]) =>
  Math.abs(pts.reduce((sum, [x, y], i) => { const [nx, ny] = pts[(i + 1) % pts.length]; return sum + x * ny - nx * y; }, 0)) / 2;

export const perimeter = (pts: Point[]) =>
  pts.reduce((sum, [x, y], i) => { const [nx, ny] = pts[(i + 1) % pts.length]; return sum + Math.hypot(nx - x, ny - y); }, 0);

export const edgeLengths = (pts: Point[]) => pts.map(([x, y], i) => { const [nx, ny] = pts[(i + 1) % pts.length]; return Math.hypot(nx - x, ny - y); });

/** A round scale-bar length (1, 2 or 5 × 10ⁿ) close to a target length in metres. */
export const niceLength = (target: number) => {
  if (target <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(target));
  const unit = target / power;
  return (unit >= 5 ? 5 : unit >= 2 ? 2 : 1) * power;
};
