import { type RoomState, stateColor } from "@/design/state";

/**
 * A room/stay state as a soft pill with a dot — the one way a state is shown (owner request 2026-10-18, decision 231:
 * no coloured side stripes). `pulse` marks what needs action (an overdue stay). `bare` drops the pill on a surface
 * that is already tinted by the state (the room card, decision 235): the dot and the label stay.
 */
export function StatusPill({ state, label, pulse = false, bare = false }: { state: RoomState; label: string; pulse?: boolean; bare?: boolean }) {
  const c = stateColor(state);
  return (
    <span className={`inline-flex h-6 items-center gap-1.5 whitespace-nowrap rounded-full text-label ${bare ? "font-medium" : `px-2.5 ${c.soft}`} ${c.text}`}>
      <span aria-hidden className={`h-1.5 w-1.5 flex-none rounded-full ${c.solid} ${pulse ? "attention" : ""}`} />
      {label}
    </span>
  );
}
