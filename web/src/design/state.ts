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

/** «محجوزة قريبًا» is an outline only (tokens: reserved-soon has no soft/solid fill). */
export const reservedSoonOutline = "border-state-reserved-soon";
