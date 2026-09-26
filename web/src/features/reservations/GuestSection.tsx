import { useQuery } from "@tanstack/react-query";
import { CircleCheck, ImageUp, Plus, Search, TriangleAlert, UserPlus, X } from "lucide-react";
import { useEffect, useState } from "react";

import { api, data } from "@/api/client";
import { Field, Section, Select, TextInput, inputClass } from "@/components/ui/form";
import { previousStays } from "@/i18n/counts";
import { t } from "@/i18n/t";

import type { Errors, Form, GuestRow, IdType } from "./model";

const RELATIONS = ["زوج", "زوجة", "ابن", "ابنة", "أب", "أم", "أخ", "أخت", "قريب"];
const NATIONALITIES = ["سوداني", "جنوب سوداني", "مصري", "إثيوبي", "إريتري", "تشادي", "سعودي", "إماراتي"];
const ID_TYPES: IdType[] = ["national_id", "passport", "driving_license", "other"];

type Props = { form: Form; errors: Errors; update: (patch: Partial<Form>) => void };

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(id);
  }, [value, ms]);
  return v;
}

/** Step 1 «النزيل»: search a registered guest (by phone first) or register a new one; collapses once picked. */
export function GuestSection({ form, errors, update }: Props) {
  if (form.guestMode === "picked" && form.picked) return <PickedGuest guest={form.picked} onChange={() => update({ guestMode: "search", picked: null })} />;
  const g = form.guest;
  const setGuest = (patch: Partial<Form["guest"]>) => update({ guest: { ...g, ...patch } });
  return (
    <Section step={1} title={t("newRes.guest")}>
      <div className="grid grid-cols-[2fr_1fr_1fr_1fr] items-end gap-3">
        <GuestSearch onPick={(guest) => update({ guestMode: "picked", picked: guest })} />
        <button
          type="button"
          onClick={() => update({ guestMode: "new" })}
          className={`inline-flex h-9 items-center justify-center gap-2 rounded-control border px-4 font-sans text-body font-semibold ${
            form.guestMode === "new" ? "border-primary bg-primary-soft text-primary" : "border-border-strong bg-bg-surface text-text-primary hover:bg-bg-surface-2"
          }`}
        >
          <UserPlus className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
          {t("newRes.newGuest")}
        </button>
        {form.guestMode === "search" && <span className="col-span-2 pb-2 text-label font-normal text-text-secondary">{t("newRes.searchTip")}</span>}
      </div>

      {form.guestMode === "new" && (
        <>
          <div className="grid grid-cols-[2fr_1fr_1fr_1fr] gap-3">
            <Field label={t("newRes.fullName")} required error={errors.full_name}>
              <TextInput autoFocus value={g.full_name} invalid={!!errors.full_name} onChange={(e) => setGuest({ full_name: e.target.value })} />
            </Field>
            <Field label={t("newRes.phone")}>
              <TextInput dir="ltr" inputMode="tel" value={g.phone} onChange={(e) => setGuest({ phone: e.target.value })} />
            </Field>
            <Field label={t("newRes.nationality")}>
              <TextInput list="nationalities" value={g.nationality} onChange={(e) => setGuest({ nationality: e.target.value })} />
              <datalist id="nationalities">
                {NATIONALITIES.map((n) => (
                  <option key={n} value={n} />
                ))}
              </datalist>
            </Field>
            <Field label={t("newRes.idType")}>
              <Select value={g.id_type} onChange={(e) => setGuest({ id_type: e.target.value as IdType | "" })}>
                <option value="">{t("newRes.choose")}</option>
                {ID_TYPES.map((k) => (
                  <option key={k} value={k}>
                    {t(`idType.${k}`)}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <div className="grid grid-cols-[2fr_1fr_1fr_1fr] items-start gap-3">
            <Field label={t("newRes.idNumber")}>
              <TextInput dir="ltr" value={g.id_number} onChange={(e) => setGuest({ id_number: e.target.value })} />
            </Field>
            <div className="col-span-2 flex flex-col gap-1.5">
              <span className="text-label text-text-secondary">
                {t("newRes.idPhoto")} <span className="text-text-disabled">{t("newRes.optional")}</span>
              </span>
              <label className="flex h-9 cursor-pointer items-center gap-2 rounded-control border border-dashed border-border-strong bg-bg-page px-3 text-body text-text-secondary">
                <ImageUp className="h-icon w-icon flex-none" strokeWidth={1.75} aria-hidden />
                <span className="truncate">{g.photo ? g.photo.name : t("newRes.idPhotoPick")}</span>
                <span className="ms-auto text-label font-normal text-text-disabled">{t("newRes.idPhotoLimit")}</span>
                <input type="file" accept="image/*" capture="environment" className="sr-only" onChange={(e) => setGuest({ photo: e.target.files?.[0] ?? null })} />
              </label>
            </div>
          </div>
          <div className="flex flex-col gap-2 pt-1">
            <span className="text-label text-text-secondary">{t("newRes.companions")}</span>
            {g.companions.map((c, i) => (
              <div key={i} className="grid max-w-[640px] grid-cols-[2fr_1fr_36px] gap-3">
                <TextInput
                  aria-label={t("newRes.companionName")}
                  value={c.name}
                  onChange={(e) => setGuest({ companions: g.companions.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)) })}
                />
                <TextInput
                  aria-label={t("newRes.relation")}
                  list="relations"
                  value={c.relation}
                  onChange={(e) => setGuest({ companions: g.companions.map((x, j) => (j === i ? { ...x, relation: e.target.value } : x)) })}
                />
                <button
                  type="button"
                  aria-label={t("newRes.removeCompanion")}
                  onClick={() => setGuest({ companions: g.companions.filter((_, j) => j !== i) })}
                  className="flex h-9 w-9 items-center justify-center rounded-control border border-border-strong bg-bg-surface text-text-secondary hover:bg-bg-surface-2"
                >
                  <X className="h-icon-inline w-icon-inline" strokeWidth={1.75} aria-hidden />
                </button>
              </div>
            ))}
            <datalist id="relations">
              {RELATIONS.map((r) => (
                <option key={r} value={r} />
              ))}
            </datalist>
            <button
              type="button"
              onClick={() => setGuest({ companions: [...g.companions, { name: "", relation: "" }] })}
              className="inline-flex w-fit items-center gap-1.5 border-0 bg-transparent p-0 font-sans text-body font-medium text-primary hover:text-primary-hover"
            >
              <Plus className="h-icon-inline w-icon-inline" strokeWidth={1.75} aria-hidden />
              {t("newRes.addCompanion")}
            </button>
          </div>
        </>
      )}
    </Section>
  );
}

function GuestSearch({ onPick }: { onPick: (g: GuestRow) => void }) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const term = useDebounced(q.trim(), 250);
  const results = useQuery({
    queryKey: ["guests", "search", term],
    queryFn: () => data(api.GET("/api/v1/guests/", { params: { query: { q: term } } })),
    enabled: term.length >= 2,
  });
  const rows = results.data?.results ?? [];
  return (
    <div className="relative flex flex-col gap-1.5">
      <span className="text-label text-text-secondary">{t("newRes.search")}</span>
      <span className={`${inputClass()} flex items-center gap-2`}>
        <Search className="h-icon w-icon flex-none text-text-secondary" strokeWidth={1.75} aria-hidden />
        <input
          value={q}
          role="combobox"
          aria-expanded={open && term.length >= 2}
          aria-label={t("newRes.search")}
          placeholder={t("newRes.searchPlaceholder")}
          onFocus={() => setOpen(true)}
          onBlur={() => window.setTimeout(() => setOpen(false), 150)}
          onChange={(e) => {
            setQ(e.target.value);
            setOpen(true);
          }}
          className="h-full w-full min-w-0 border-0 bg-transparent p-0 font-sans text-body text-text-primary outline-none placeholder:text-text-disabled"
        />
      </span>
      {open && term.length >= 2 && results.isSuccess && (
        <ul role="listbox" className="absolute inset-x-0 top-full z-20 m-0 mt-1 max-h-72 list-none overflow-auto rounded-control border border-border bg-bg-surface p-1 shadow-elevated">
          {rows.length === 0 && <li className="px-3 py-2 text-body text-text-secondary">{t("newRes.noResults")}</li>}
          {rows.map((g) => (
            <li key={g.id}>
              <button
                type="button"
                role="option"
                aria-selected={false}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  onPick(g);
                  setOpen(false);
                }}
                className="flex w-full flex-col items-start rounded-control border-0 bg-transparent px-3 py-2 text-start font-sans hover:bg-bg-surface-2"
              >
                <span className="text-body font-medium text-text-primary">{g.full_name}</span>
                <span className="text-label font-normal text-text-secondary">
                  {g.phone && <span dir="ltr">{g.phone}</span>}
                  {g.phone && " · "}
                  {previousStays(g.stays_count)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function PickedGuest({ guest, onChange }: { guest: GuestRow; onChange: () => void }) {
  return (
    <section className="flex flex-wrap items-center gap-3 rounded-card border border-border bg-bg-surface p-4">
      <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-success-soft text-success-text">
        <CircleCheck className="h-icon-inline w-icon-inline" strokeWidth={1.75} aria-hidden />
      </span>
      <h2 className="m-0 text-section-title">{t("newRes.guest")}</h2>
      <span className="text-body">{guest.full_name}</span>
      <span className="text-body text-text-secondary">
        {guest.phone && (
          <>
            <span dir="ltr">{guest.phone}</span> ·{" "}
          </>
        )}
        {guest.nationality && `${guest.nationality} · `}
        {previousStays(guest.stays_count)}
      </span>
      {guest.warning_note && (
        <span className="inline-flex h-6 items-center gap-1.5 rounded-control bg-warning-soft px-2 text-label text-warning-text">
          <TriangleAlert className="h-icon-inline w-icon-inline" strokeWidth={1.75} aria-hidden />
          {t("newRes.warning", { note: guest.warning_note })}
        </span>
      )}
      <button type="button" onClick={onChange} className="ms-auto border-0 bg-transparent p-0 font-sans text-body font-medium text-primary hover:text-primary-hover">
        {t("newRes.change")}
      </button>
    </section>
  );
}
