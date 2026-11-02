import * as RSelect from "@radix-ui/react-select";
import { animate, motion, useMotionValue, useTransform } from "motion/react";
import { useEffect, useId, type ReactNode } from "react";

export function Label({ children, htmlFor }: { children: ReactNode; htmlFor?: string }) {
  return <label htmlFor={htmlFor} className="mono-label block">{children}</label>;
}

export function Field({ label, value, onChange, unit, hint, placeholder, type = "text", disabled, testId, error }: {
  label: string; value: string; onChange: (v: string) => void; unit?: string; hint?: ReactNode; placeholder?: string; type?: "text" | "number"; disabled?: boolean; testId?: string; error?: string | null;
}) {
  const id = useId();
  return (
    <div className={disabled ? "opacity-40" : ""}>
      <Label htmlFor={id}>{label}</Label>
      <div className="group relative mt-1.5 flex items-baseline border-b border-rule transition-colors focus-within:border-ink hover:border-soft">
        <input id={id} data-testid={testId} type={type} min={type === "number" ? 0 : undefined} step="any" inputMode={type === "number" ? "decimal" : undefined} value={value} placeholder={placeholder} disabled={disabled} aria-invalid={!!error}
          onChange={(e) => onChange(e.target.value)} className={`w-full bg-transparent py-1.5 text-[15px] outline-none placeholder:text-faint ${type === "number" ? "font-mono tnum" : ""}`} />
        {unit && <span className="pl-2 font-mono text-xs text-faint">{unit}</span>}
      </div>
      {error ? <p className="mt-1.5 text-xs font-medium">{error}</p> : hint ? <p className="mt-1.5 text-xs leading-relaxed text-soft">{hint}</p> : null}
    </div>
  );
}

export function Select({ label, value, onChange, options, placeholder = "Select", hint, testId, disabled }: {
  label: string; value: string; onChange: (v: string) => void; options: { value: string; label: string; note?: string; group?: string | null }[]; placeholder?: string; hint?: ReactNode; testId?: string; disabled?: boolean;
}) {
  const id = useId();
  const groups = [...new Set(options.map((o) => o.group ?? ""))];
  return (
    <div className={disabled ? "opacity-40" : ""}>
      <Label htmlFor={id}>{label}</Label>
      <RSelect.Root value={value || undefined} onValueChange={onChange} disabled={disabled}>
        <RSelect.Trigger id={id} data-testid={testId} className="mt-1.5 flex w-full items-center justify-between gap-3 border-b border-rule bg-transparent py-1.5 text-left text-[15px] outline-none transition-colors hover:border-soft focus:border-ink data-[placeholder]:text-faint">
          <span className="truncate"><RSelect.Value placeholder={placeholder} /></span>
          <RSelect.Icon><svg width="10" height="6" viewBox="0 0 10 6" aria-hidden><path d="M0 0.5 5 5.5 10 0.5" fill="none" stroke="currentColor" /></svg></RSelect.Icon>
        </RSelect.Trigger>
        <RSelect.Portal>
          <RSelect.Content position="popper" sideOffset={6} className="z-50 max-h-[50vh] w-[var(--radix-select-trigger-width)] min-w-64 overflow-hidden border border-ink bg-sheet text-ink shadow-[6px_6px_0_rgb(0_0_0/0.1)]">
            <RSelect.Viewport className="p-1">
              {groups.map((group) => (
                <RSelect.Group key={group}>
                  {group && <RSelect.Label className="mono-label px-2 pb-1 pt-3">{group}</RSelect.Label>}
                  {options.filter((o) => (o.group ?? "") === group).map((o) => (
                    <RSelect.Item key={o.value} value={o.value} className="flex cursor-pointer flex-col px-2 py-1.5 text-sm outline-none data-[highlighted]:bg-ink data-[highlighted]:text-invert">
                      <RSelect.ItemText>{o.label}</RSelect.ItemText>
                      {o.note && <span className="text-[11px] opacity-60">{o.note}</span>}
                    </RSelect.Item>
                  ))}
                </RSelect.Group>
              ))}
            </RSelect.Viewport>
          </RSelect.Content>
        </RSelect.Portal>
      </RSelect.Root>
      {hint && <p className="mt-1.5 text-xs leading-relaxed text-soft">{hint}</p>}
    </div>
  );
}

export function Segmented<T extends string>({ label, value, onChange, options, testId, compact }: { label?: string; value: T; onChange: (v: T) => void; options: { value: T; label: string }[]; testId?: string; compact?: boolean }) {
  const name = useId();
  return (
    <div>
      {label && <span className="mono-label mb-1.5 block">{label}</span>}
      <div role="radiogroup" aria-label={label} data-testid={testId} className="inline-flex border border-rule">
        {options.map((o) => {
          const active = o.value === value;
          return (
            <button key={o.value} type="button" role="radio" aria-checked={active} data-value={o.value} onClick={() => onChange(o.value)} className={`relative whitespace-nowrap ${compact ? "px-2.5 py-1 text-xs" : "px-3 py-1.5 text-[13px]"} transition-colors ${active ? "text-invert" : "text-soft hover:text-ink"}`}>
              {active && <motion.span layoutId={name} className="absolute inset-0 bg-ink" transition={{ duration: 0.28 }} />}
              <span className="relative">{o.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function Check({ label, checked, onChange, hint, testId }: { label: string; checked: boolean; onChange: (v: boolean) => void; hint?: ReactNode; testId?: string }) {
  return (
    <label className="flex cursor-pointer items-start gap-3">
      <input type="checkbox" data-testid={testId} checked={checked} onChange={(e) => onChange(e.target.checked)} className="peer sr-only" />
      <span aria-hidden className={`mt-0.5 flex size-4 shrink-0 items-center justify-center border transition-colors peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-ink ${checked ? "border-ink bg-ink" : "border-soft"}`}>
        {checked && <svg width="10" height="8" viewBox="0 0 10 8"><motion.path initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.2 }} d="M1 4 3.8 6.8 9 1" fill="none" stroke="var(--invert)" strokeWidth="1.6" /></svg>}
      </span>
      <span><span className="text-[13.5px]">{label}</span>{hint && <span className="mt-0.5 block text-xs leading-relaxed text-soft">{hint}</span>}</span>
    </label>
  );
}

export function Button({ children, variant = "solid", className = "", ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "solid" | "line" | "quiet" }) {
  const styles = {
    solid: "bg-ink text-invert hover:opacity-85 disabled:opacity-30",
    line: "border border-ink text-ink hover:bg-ink hover:text-invert disabled:border-rule disabled:text-faint disabled:hover:bg-transparent",
    quiet: "text-soft hover:text-ink disabled:text-faint",
  }[variant];
  return <button type="button" {...props} className={`inline-flex items-center justify-center gap-2 px-4 py-2.5 text-[13px] font-medium transition-all duration-200 active:translate-y-px ${styles} ${className}`}>{children}</button>;
}

export function Note({ children, tone = "plain", testId }: { children: ReactNode; tone?: "plain" | "strong"; testId?: string }) {
  return <div data-testid={testId} role={tone === "strong" ? "alert" : undefined} className={`border-l-2 py-1 pl-3 text-[13px] leading-relaxed ${tone === "strong" ? "border-ink font-medium" : "border-rule text-soft"}`}>{children}</div>;
}

export function Panel({ title, aside, children, className = "" }: { title?: string; aside?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`border-t border-ink pt-3 ${className}`}>
      {title && <div className="mb-5 flex items-baseline justify-between gap-4"><h3 className="mono-label !text-ink">{title}</h3>{aside}</div>}
      {children}
    </section>
  );
}

export function Row({ k, v, mono = true }: { k: string; v: ReactNode; mono?: boolean }) {
  return <div className="flex items-baseline justify-between gap-6 border-b border-rule py-2"><span className="text-[13px] text-soft">{k}</span><span className={`text-right text-[13px] ${mono ? "font-mono tnum" : ""}`}>{v}</span></div>;
}

/** Counts to a value when it changes, so a recalculated figure reads as changed. */
export function CountUp({ value, digits = 0, className, testId }: { value: number; digits?: number; className?: string; testId?: string }) {
  const motionValue = useMotionValue(value);
  const text = useTransform(motionValue, (v) => v.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits }));
  useEffect(() => { const c = animate(motionValue, value, { duration: 0.7, ease: [0.22, 1, 0.36, 1] }); return () => c.stop(); }, [value, motionValue]);
  return <motion.span data-testid={testId} data-value={value} className={className}>{text}</motion.span>;
}
