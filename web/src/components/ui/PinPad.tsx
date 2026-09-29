import { t } from "@/i18n/t";

export const PIN_LENGTH = 6;
export const PIN_MIN = 4;

/** Six dots: filled for each digit typed (login 6.1, session lock 6.14). */
export function PinDots({ count }: { count: number }) {
  return (
    <div className="flex gap-3.5" role="status" aria-label={t("login.pinDots", { n: count })}>
      {Array.from({ length: PIN_LENGTH }, (_, i) => (
        <span
          key={i}
          className={`h-3.5 w-3.5 rounded-full border-[1.5px] ${i < count ? "border-primary bg-primary" : "border-border-strong bg-bg-surface"}`}
        />
      ))}
    </div>
  );
}

type Props = {
  onDigit: (digit: string) => void;
  onClear: () => void;
  onBackspace: () => void;
  /** «دخول»: a PIN of 4 or 5 digits is sent with it; six digits go by themselves (review 2026-09-28, UI-5). */
  onEnter?: () => void;
  canEnter?: boolean;
  disabled?: boolean;
};

/**
 * 1-2-3 grid laid out left to right like a calculator or phone keypad: `dir="ltr"` on the grid only
 * (RTL notes «لوحة الأرقام»), with «مسح» and ⌫ on the last row.
 */
export function PinPad({ onDigit, onClear, onBackspace, onEnter, canEnter = false, disabled = false }: Props) {
  const digit = disabled
    ? "border border-border bg-bg-surface-2 text-text-disabled"
    : "border border-border-strong bg-bg-surface text-text-primary hover:bg-bg-surface-2";
  const action = `border-0 bg-transparent text-body font-semibold ${disabled ? "text-text-disabled" : "text-text-secondary hover:bg-bg-surface-2"}`;
  const key = "flex h-[60px] items-center justify-center rounded-control font-sans disabled:cursor-not-allowed";
  return (
    <div dir="ltr" className="grid grid-cols-[repeat(3,88px)] gap-2">
      {["1", "2", "3", "4", "5", "6", "7", "8", "9"].map((d) => (
        <button key={d} type="button" disabled={disabled} onClick={() => onDigit(d)} className={`${key} ${digit} text-[22px] font-semibold`}>
          {d}
        </button>
      ))}
      <button type="button" disabled={disabled} onClick={onClear} className={`${key} ${action}`}>
        {t("login.clear")}
      </button>
      <button type="button" disabled={disabled} onClick={() => onDigit("0")} className={`${key} ${digit} text-[22px] font-semibold`}>
        0
      </button>
      <button type="button" disabled={disabled} onClick={onBackspace} aria-label={t("login.backspace")} className={`${key} ${action}`}>
        ⌫
      </button>
      {onEnter && (
        <button
          type="button"
          disabled={disabled || !canEnter}
          onClick={onEnter}
          className="col-span-3 flex h-12 items-center justify-center rounded-control border-0 bg-primary font-sans text-body font-semibold text-primary-text-on disabled:bg-bg-surface-2 disabled:text-text-disabled"
        >
          {t("login.enterPin")}
        </button>
      )}
    </div>
  );
}
