import { CircleAlert } from "lucide-react";
import { forwardRef, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from "react";
import { ChevronDown } from "lucide-react";

import { toWestern } from "@/i18n/digits";
import { t } from "@/i18n/t";

/** Numbered form section (6.4): 28 px step badge + 16/600 title. */
export function Section({
  step,
  title,
  done = false,
  note,
  children,
}: {
  step: number;
  title: string;
  done?: boolean;
  note?: string;
  children?: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-3 rounded-card border border-border bg-bg-surface p-4">
      <div className="flex items-center gap-3">
        <span
          className={`inline-flex h-7 w-7 items-center justify-center rounded-full text-body font-semibold ${
            done ? "bg-success-soft text-success-text" : children ? "bg-primary text-primary-text-on" : "bg-bg-surface-2 text-text-disabled"
          }`}
        >
          {step}
        </span>
        <h2 className={`m-0 text-section-title ${children ? "" : "text-text-disabled"}`}>{title}</h2>
        {note && <span className="text-label font-normal text-text-disabled">{note}</span>}
      </div>
      {children}
    </section>
  );
}

type FieldProps = {
  label: ReactNode;
  required?: boolean;
  error?: string | null;
  hint?: ReactNode;
  className?: string;
  children: ReactNode;
  action?: ReactNode;
};

/** Label 12/500 above the control, red label + message below when invalid (6.4 B). */
export function Field({ label, required, error, hint, className = "", children, action }: FieldProps) {
  return (
    <label className={`flex min-w-0 flex-col gap-1.5 ${className}`}>
      <span className={`flex justify-between text-label ${error ? "text-danger" : "text-text-secondary"}`}>
        <span>
          {label}
          {required && <span className="text-danger"> *</span>}
        </span>
        {action}
      </span>
      {children}
      {error ? (
        <span className="text-label font-normal text-danger">{error}</span>
      ) : (
        hint && <span className="text-label font-normal text-text-secondary">{hint}</span>
      )}
    </label>
  );
}

export const inputClass = (invalid = false, readOnly = false) =>
  `h-9 w-full min-w-0 rounded-control border px-3 font-sans text-body text-text-primary placeholder:text-text-disabled ${
    invalid ? "border-danger" : readOnly ? "border-border bg-bg-surface-2" : "border-border-strong bg-bg-surface"
  }`;

export const TextInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }>(
  function TextInput({ invalid, ...rest }, ref) {
    return <input ref={ref} {...rest} className={`${inputClass(invalid, rest.readOnly)} ${rest.className ?? ""}`} />;
  },
);

/** «1500000» → «1,500,000» as it is typed, keeping the caret after the same digit. Anything that is not a plain
 *  amount (a sign, letters) is left for the caller's validation. */
export function groupThousands(el: HTMLInputElement) {
  const raw = el.value;
  const plain = toWestern(raw).replace(/[,٬\s]/g, "");
  if (!/^\d*(\.\d{0,2})?$/.test(plain)) return;
  const [whole, fraction] = plain.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",") + (fraction === undefined ? "" : `.${fraction}`);
  if (grouped === raw) return;
  const caret = el.selectionStart ?? raw.length;
  const before = toWestern(raw.slice(0, caret)).replace(/[^\d.]/g, "").length;
  let pos = 0;
  for (let seen = 0; pos < grouped.length && seen < before; pos++) if (/[\d.]/.test(grouped[pos])) seen++;
  el.value = grouped;
  el.setSelectionRange(pos, pos);
}

/** Money typed in currency units («15,000»), shown with the «ج.س» suffix; the caller parses it.
 *  Wide enough for «100,000,000 ج.س» wherever it is placed (review 2026-09-28: fields too small for big amounts). */
export function MoneyInput({ invalid, onChange, suffix, ...rest }: InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean; suffix?: string }) {
  return (
    <span
      className={`flex h-9 min-w-[10.5rem] items-center justify-between gap-2 rounded-control border px-3 focus-within:border-primary ${
        invalid ? "border-danger bg-bg-surface" : rest.readOnly ? "border-border bg-bg-surface-2" : "border-border-strong bg-bg-surface"
      }`}
    >
      <input
        inputMode="decimal"
        {...rest}
        onChange={(e) => {
          groupThousands(e.target);
          onChange?.(e);
        }}
        className="h-full w-full min-w-0 border-0 bg-transparent p-0 font-sans text-body text-text-primary outline-none placeholder:text-text-disabled"
      />
      <span className="flex-none text-body text-text-secondary">{suffix ?? t("money.currency")}</span>
    </span>
  );
}

export function Select({ invalid, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement> & { invalid?: boolean }) {
  return (
    <span className="relative flex">
      <select {...rest} className={`${inputClass(invalid)} appearance-none pe-9`}>
        {children}
      </select>
      <ChevronDown
        className="pointer-events-none absolute end-3 top-2.5 h-icon-inline w-icon-inline text-text-secondary"
        strokeWidth={1.75}
        aria-hidden
      />
    </span>
  );
}

/** Segmented control (نوع المدة، طريقة الدفع): equal-width options, selected one on primary-soft. */
export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex h-9 overflow-hidden rounded-control border border-border-strong bg-bg-surface">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
          className={`flex flex-1 items-center justify-center whitespace-nowrap border-0 border-border px-3 font-sans text-body [&:not(:first-child)]:border-s ${
            o.value === value ? "bg-primary-soft font-semibold text-primary" : "bg-bg-surface text-text-primary hover:bg-bg-surface-2"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function ErrorBanner({ children }: { children: ReactNode }) {
  return (
    <div role="alert" className="flex min-h-11 items-center gap-3 rounded-card bg-danger-soft px-4 py-2 text-body font-medium text-danger-text">
      <CircleAlert className="h-icon w-icon flex-none" strokeWidth={1.75} aria-hidden />
      <span>{children}</span>
    </div>
  );
}
