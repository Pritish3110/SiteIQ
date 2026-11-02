import type { CheckStatus } from "../lib/types";
import { STATUS_LABEL } from "../lib/format";

/** Status is carried by shape as well as text, so it survives greyscale printing. */
export function StatusMark({ status, size = 14 }: { status: CheckStatus; size?: number }) {
  const props = { width: size, height: size, viewBox: "0 0 14 14", "aria-hidden": true, className: "shrink-0" };
  switch (status) {
    case "PASS": return <svg {...props}><circle cx="7" cy="7" r="6" fill="none" stroke="currentColor" /><path d="M4 7.2 6.2 9.4 10 5" fill="none" stroke="currentColor" strokeWidth="1.3" /></svg>;
    case "FAIL": return <svg {...props}><rect width="14" height="14" fill="currentColor" /><path d="M4 4 10 10M10 4 4 10" stroke="var(--sheet)" strokeWidth="1.6" /></svg>;
    case "NEEDS_INPUT": return <svg {...props}><rect x=".5" y=".5" width="13" height="13" fill="none" stroke="currentColor" strokeDasharray="2.5 2" /></svg>;
    case "REFER": return <svg {...props}><circle cx="7" cy="7" r="6" fill="none" stroke="currentColor" /><path d="M7 1a6 6 0 0 1 0 12z" fill="currentColor" /></svg>;
    default: return <svg {...props}><circle cx="7" cy="7" r="6" fill="none" stroke="currentColor" /><path d="M3 11 11 3" stroke="currentColor" /></svg>;
  }
}
export const StatusTag = ({ status }: { status: CheckStatus }) => (
  <span className="inline-flex items-center gap-1.5 self-start font-mono text-[11px] whitespace-nowrap"><StatusMark status={status} size={12} />{STATUS_LABEL[status]}</span>
);
