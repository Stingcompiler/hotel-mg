/** Room/stay state colours are semantic only (spec §10.2): this helper is the one place that uses them. */
export type RoomState = "ready" | "occupied" | "cleaning" | "maintenance" | "overdue";

const CLASSES: Record<RoomState, { solid: string; soft: string; text: string; border: string }> = {
  ready: { solid: "bg-state-ready", soft: "bg-state-ready-soft", text: "text-state-ready-text", border: "border-state-ready" },
  occupied: {
    solid: "bg-state-occupied",
    soft: "bg-state-occupied-soft",
    text: "text-state-occupied-text",
    border: "border-state-occupied",
  },
  cleaning: {
    solid: "bg-state-cleaning",
    soft: "bg-state-cleaning-soft",
    text: "text-state-cleaning-text",
    border: "border-state-cleaning",
  },
  maintenance: {
    solid: "bg-state-maintenance",
    soft: "bg-state-maintenance-soft",
    text: "text-state-maintenance-text",
    border: "border-state-maintenance",
  },
  overdue: {
    solid: "bg-state-overdue",
    soft: "bg-state-overdue-soft",
    text: "text-state-overdue-text",
    border: "border-state-overdue",
  },
};

export function stateColor(state: RoomState) {
  return CLASSES[state];
}

/**
 * A room card's surface: its state's soft shade, softened further into the card colour so a board of 30 rooms stays
 * calm (owner request 2026-10-22, decision 235). The same mix works in the dark theme.
 */
const TINT: Record<RoomState, string> = {
  ready: "bg-[color-mix(in_srgb,var(--color-state-ready-soft)_60%,var(--color-bg-surface))]",
  occupied: "bg-[color-mix(in_srgb,var(--color-state-occupied-soft)_60%,var(--color-bg-surface))]",
  cleaning: "bg-[color-mix(in_srgb,var(--color-state-cleaning-soft)_60%,var(--color-bg-surface))]",
  maintenance: "bg-[color-mix(in_srgb,var(--color-state-maintenance-soft)_60%,var(--color-bg-surface))]",
  overdue: "bg-[color-mix(in_srgb,var(--color-state-overdue-soft)_60%,var(--color-bg-surface))]",
};

export function stateTint(state: RoomState): string {
  return TINT[state];
}

/** «محجوزة قريبًا» is an outline only (tokens: reserved-soon has no soft/solid fill). */
export const reservedSoon = {
  outline: "outline outline-2 -outline-offset-2 outline-state-reserved-soon",
  text: "text-state-reserved-soon",
  border: "border-[1.5px] border-state-reserved-soon",
};

/** History timeline dots and the card's start stripe use the solid colour of a room status. */
export function stateSolid(state: RoomState | "overdue"): string {
  return CLASSES[state].solid;
}
