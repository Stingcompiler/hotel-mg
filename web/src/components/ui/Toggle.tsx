/** On/off switch (settings rows): 36×20 track, primary when on. The knob sits at the inline end when on. */
export function Toggle({
  checked,
  onChange,
  label,
  disabled = false,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-5 w-9 flex-none items-center rounded-full border-0 p-0 transition-colors disabled:opacity-60 ${
        checked ? "bg-primary" : "bg-border-strong"
      }`}
    >
      <span
        className={`absolute top-0.5 h-4 w-4 rounded-full bg-bg-surface shadow-elevated transition-all ${checked ? "end-0.5" : "start-0.5"}`}
      />
    </button>
  );
}
