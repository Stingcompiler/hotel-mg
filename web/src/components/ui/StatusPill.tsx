import { type RoomState, stateColor } from "@/design/state";

/**
 * A room/stay state as a soft pill with a dot — the one way a state is shown (owner request 2026-10-18, decision 231:
 * no coloured side stripes). `pulse` marks what needs action (an overdue stay).
 */
export function StatusPill({ state, label, pulse = false }: { state: RoomState; label: string; pulse?: boolean }) {
  const c = stateColor(state);
  return (
    <span className={`inline-flex h-6 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 text-label ${c.soft} ${c.text}`}>
      <span aria-hidden className={`h-1.5 w-1.5 flex-none rounded-full ${c.solid} ${pulse ? "attention" : ""}`} />
      {label}
    </span>
  );
}
