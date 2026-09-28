import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useMemo, useState } from "react";

import type { components } from "@api/schema";

import { api, data } from "@/api/client";
import { keys } from "@/api/queries";
import { ErrorBanner, Select, TextInput } from "@/components/ui/form";
import { Toggle } from "@/components/ui/Toggle";
import { stateColor } from "@/design/state";
import { digits, toWestern } from "@/i18n/digits";
import { t } from "@/i18n/t";

import { ROOM_TYPES } from "./RoomTypesTab";
import { apiErrorText, Card, Footnote, HeadRow, linkButton, smallButton } from "./shared";

type Room = components["schemas"]["Room"];
type Draft = { number: string; name: string; floor: string; room_type: string; note: string; in_service: boolean };
const GRID = "grid grid-cols-[72px_minmax(90px,1.2fr)_64px_130px_minmax(120px,2fr)_80px_90px] items-center gap-3 px-4";
const ROOMS = ["rooms", "settings"] as const;

/** V2 6.11 C «الغرف»: rooms by floor, edited in place (type, note, in service). */
export function RoomsTab({ readOnly }: { readOnly: boolean }) {
  const queryClient = useQueryClient();
  const rooms = useQuery({ queryKey: ROOMS, queryFn: () => data(api.GET("/api/v1/rooms/")) });
  const types = useQuery({ queryKey: ROOM_TYPES, queryFn: () => data(api.GET("/api/v1/room-types/")) });
  const [floor, setFloor] = useState<string>("");
  const [editing, setEditing] = useState<string | "new" | null>(null);
  const [draft, setDraft] = useState<Draft>({ number: "", name: "", floor: "", room_type: "", note: "", in_service: true });
  const [error, setError] = useState<string | null>(null);

  const all = rooms.data ?? [];
  const floors = useMemo(() => [...new Set(all.map((r) => r.floor))].sort((a, b) => a - b), [all]);
  const shown = all.filter((r) => floor === "" || String(r.floor) === floor);

  const start = (r: Room | null) => {
    setError(null);
    setDraft(
      r
        ? { number: r.number, name: r.name, floor: String(r.floor), room_type: r.room_type, note: r.note, in_service: r.in_service }
        : { number: "", name: "", floor: floor || String(floors[0] ?? 1), room_type: types.data?.[0]?.id ?? "", note: "", in_service: true },
    );
    setEditing(r ? r.id : "new");
  };

  const save = useMutation({
    mutationFn: () => {
      const body = { number: draft.number.trim(), name: draft.name.trim(), floor: Number(draft.floor), room_type: draft.room_type, note: draft.note.trim() };
      if (editing === "new") return data(api.POST("/api/v1/rooms/", { body }));
      const current = all.find((r) => r.id === editing)!;
      return data(
        api.PATCH("/api/v1/rooms/{id}", {
          params: { path: { id: current.id } },
          body: { ...body, in_service: draft.in_service, version: current.version },
        }),
      );
    },
    onSuccess: () => {
      setEditing(null);
      void queryClient.invalidateQueries({ queryKey: ["rooms"] });
      void queryClient.invalidateQueries({ queryKey: ROOM_TYPES });
      void queryClient.invalidateQueries({ queryKey: keys.roomBoard });
    },
    onError: (e) => setError(apiErrorText(e)),
  });

  const rows: (Room | null)[] = [...shown, ...(editing === "new" ? [null] : [])];
  const valid = draft.number.trim() && draft.floor !== "" && draft.room_type;

  return (
    <Card
      title={t("settings.tabs.rooms")}
      note={t("settings.rooms.count", { rooms: digits(String(all.length)), floors: digits(String(floors.length)) })}
      actions={
        <>
          <div className="w-36">
            <Select aria-label={t("settings.rooms.floor")} value={floor} onChange={(e) => setFloor(e.target.value)}>
              <option value="">{t("settings.rooms.allFloors")}</option>
              {floors.map((f) => (
                <option key={f} value={String(f)}>
                  {t("settings.rooms.floorN", { n: digits(String(f)) })}
                </option>
              ))}
            </Select>
          </div>
          {!readOnly && (
            <button type="button" disabled={editing !== null} onClick={() => start(null)} className={smallButton()}>
              <Plus className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
              {t("settings.rooms.new")}
            </button>
          )}
        </>
      }
    >
      {error && (
        <div className="p-4 pb-0">
          <ErrorBanner>{error}</ErrorBanner>
        </div>
      )}
      <HeadRow grid={GRID} labels={["number", "type", "floor", "state", "note", "service", ""].map((k) => (k ? t(`settings.rooms.col_${k}`) : ""))} />
      <div className="min-h-0 flex-1 overflow-auto">
        {rows.map((r) => {
          const isEditing = r ? editing === r.id : true;
          const chip = r && <StateChip room={r} />;
          const note = r ? (r.status === "maintenance" && r.maintenance_reason ? r.maintenance_reason : r.note) : "";
          if (isEditing) {
            return (
              <div key={r?.id ?? "new"} className={`${GRID} min-h-[60px] border-b border-border bg-primary-soft py-2 text-table-cell`}>
                <TextInput aria-label={t("settings.rooms.col_number")} value={draft.number} onChange={(e) => setDraft({ ...draft, number: toWestern(e.target.value) })} />
                <div className="flex flex-col gap-1.5">
                  <Select aria-label={t("settings.rooms.col_type")} value={draft.room_type} onChange={(e) => setDraft({ ...draft, room_type: e.target.value })}>
                    {(types.data ?? []).map((ty) => (
                      <option key={ty.id} value={ty.id}>
                        {ty.name}
                      </option>
                    ))}
                  </Select>
                  <TextInput
                    aria-label={t("settings.rooms.name")}
                    placeholder={t("settings.rooms.name")}
                    maxLength={60}
                    value={draft.name}
                    onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                  />
                </div>
                <TextInput
                  aria-label={t("settings.rooms.col_floor")}
                  inputMode="numeric"
                  value={draft.floor}
                  onChange={(e) => setDraft({ ...draft, floor: toWestern(e.target.value).replace(/[^\d-]/g, "") })}
                />
                <div>{chip}</div>
                <TextInput aria-label={t("settings.rooms.col_note")} value={draft.note} onChange={(e) => setDraft({ ...draft, note: e.target.value })} />
                <div>
                  {r ? (
                    <Toggle checked={draft.in_service} label={t("settings.rooms.col_service")} onChange={(in_service) => setDraft({ ...draft, in_service })} />
                  ) : (
                    t("settings.yes")
                  )}
                </div>
                <div className="flex gap-2">
                  <button type="button" disabled={!valid || save.isPending} onClick={() => save.mutate()} className={smallButton("primary")}>
                    {t("settings.save")}
                  </button>
                  <button type="button" onClick={() => setEditing(null)} className={linkButton}>
                    {t("common.cancel")}
                  </button>
                </div>
              </div>
            );
          }
          return (
            <div key={r!.id} className={`${GRID} h-11 border-b border-border text-table-cell ${r!.in_service ? "" : "text-text-disabled"}`}>
              <div className="font-semibold">{digits(r!.number)}</div>
              <div className="min-w-0">
                <div className="truncate">{r!.room_type_name}</div>
                {r!.name && <div className="truncate text-label font-normal text-text-secondary">{r!.name}</div>}
              </div>
              <div>{digits(String(r!.floor))}</div>
              <div>{chip}</div>
              <div className="truncate text-text-secondary">{note || "—"}</div>
              <div>{t(r!.in_service ? "settings.yes" : "settings.no")}</div>
              <div>
                {!readOnly && (
                  <button type="button" disabled={editing !== null} onClick={() => start(r)} className={linkButton}>
                    {t("settings.edit")}
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
      <Footnote>{t("settings.rooms.footnote")}</Footnote>
    </Card>
  );
}

function StateChip({ room }: { room: Room }) {
  if (!room.in_service) {
    return <span className="inline-flex h-6 items-center rounded-control bg-bg-surface-2 px-2 text-label text-text-secondary">{t("settings.rooms.off")}</span>;
  }
  const c = stateColor(room.status);
  return <span className={`inline-flex h-6 items-center rounded-control px-2 text-label ${c.soft} ${c.text}`}>{t(`roomState.${room.status}`)}</span>;
}
