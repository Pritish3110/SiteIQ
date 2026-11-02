export const area = (v: number | null | undefined, digits = 0) =>
  v == null || !Number.isFinite(v) ? "—" : `${v.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits })} m²`;
export const metres = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? "—" : `${Number(v.toFixed(2))} m`);
export const ratio = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? "—" : v.toFixed(2));
/** Parses a text field to a positive number; blanks and junk become null so they are never sent as zero. */
export const positive = (text: string): number | null => {
  const value = Number(text.trim());
  return text.trim() !== "" && Number.isFinite(value) && value > 0 ? value : null;
};
export const STATUS_LABEL = { PASS: "Pass", FAIL: "Fail", NEEDS_INPUT: "Needs input", REFER: "Confirm", NOT_CONFIGURED: "Not configured" } as const;
export const VERDICT_LABEL = { BLOCKED: "Blocked", INCOMPLETE: "Incomplete", PROVISIONAL: "Provisional", READY_FOR_REVIEW: "Ready for review" } as const;
export const SOURCE_STATUS_LABEL: Record<string, string> = {
  verified_operative: "Verified operative",
  partially_verified: "Partly verified",
  official_source_found_pending_review: "Source compared, review pending",
  secondary_source_candidate: "Secondary source, provisional",
  not_configured: "No rules configured",
};
export const humanise = (s: string | null | undefined) => (s ?? "").replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
