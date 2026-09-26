import { Plus, X } from "lucide-react";
import { useState } from "react";

import type { components } from "@api/schema";

import { api, ApiError, data } from "@/api/client";
import { ErrorBanner, Field, Select, TextInput } from "@/components/ui/form";
import { buttons, Modal } from "@/components/ui/Modal";
import { t } from "@/i18n/t";

type Guest = components["schemas"]["Guest"];
type IdType = components["schemas"]["IdTypeEnum"];
const ID_TYPES: IdType[] = ["national_id", "passport", "driving_license", "other"];

/** Register or edit a guest (same fields as step 1 of 6.4, plus the warning note). */
export function GuestFormModal({ guest, focusNote = false, onClose, onDone }: { guest?: Guest; focusNote?: boolean; onClose: () => void; onDone: (id: string) => void }) {
  const [f, setF] = useState({
    full_name: guest?.full_name ?? "",
    phone: guest?.phone ?? "",
    nationality: guest?.nationality ?? t("newRes.nationalityDefault"),
    id_type: (guest?.id_type ?? "") as IdType | "",
    id_number: "",
    warning_note: guest?.warning_note ?? "",
    companions: ((guest?.companions ?? []) as { name?: string; relation?: string }[]).map((c) => ({ name: c.name ?? "", relation: c.relation ?? "" })),
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (patch: Partial<typeof f>) => setF((x) => ({ ...x, ...patch }));

  const save = async () => {
    if (f.full_name.trim().split(/\s+/).length < 2) return setError(t("newRes.errFullName"));
    setBusy(true);
    setError(null);
    const body = {
      full_name: f.full_name.trim(),
      phone: f.phone.trim(),
      nationality: f.nationality.trim(),
      id_type: f.id_type,
      warning_note: f.warning_note.trim(),
      companions: f.companions.filter((c) => c.name.trim()),
      // Reception sees a masked number: only send it when typed.
      ...(f.id_number.trim() ? { id_number: f.id_number.trim() } : {}),
    };
    try {
      const saved = guest
        ? await data(api.PATCH("/api/v1/guests/{id}", { params: { path: { id: guest.id } }, body: { ...body, version: guest.version } }))
        : await data(api.POST("/api/v1/guests/", { body }));
      onDone(saved.id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("errors.error"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={guest ? t("guests.formEdit") : t("guests.formNew")}
      onClose={onClose}
      width={640}
      footer={
        <>
          <button type="button" disabled={busy} onClick={() => void save()} className={buttons.primary}>
            {t("guests.save")}
          </button>
          <div className="flex-1" />
          <button type="button" onClick={onClose} className={buttons.ghost}>
            {t("common.cancel")}
          </button>
        </>
      }
    >
      <div className="grid grid-cols-2 gap-3">
        <Field label={t("newRes.fullName")} required className="col-span-2">
          <TextInput autoFocus={!focusNote} value={f.full_name} onChange={(e) => set({ full_name: e.target.value })} />
        </Field>
        <Field label={t("newRes.phone")}>
          <TextInput dir="ltr" inputMode="tel" value={f.phone} onChange={(e) => set({ phone: e.target.value })} />
        </Field>
        <Field label={t("newRes.nationality")}>
          <TextInput value={f.nationality} onChange={(e) => set({ nationality: e.target.value })} />
        </Field>
        <Field label={t("newRes.idType")}>
          <Select value={f.id_type} onChange={(e) => set({ id_type: e.target.value as IdType | "" })}>
            <option value="">{t("newRes.choose")}</option>
            {ID_TYPES.map((k) => (
              <option key={k} value={k}>
                {t(`idType.${k}`)}
              </option>
            ))}
          </Select>
        </Field>
        <Field label={t("newRes.idNumber")} hint={guest?.id_number ? <span dir="ltr">{guest.id_number}</span> : undefined}>
          <TextInput dir="ltr" value={f.id_number} onChange={(e) => set({ id_number: e.target.value })} />
        </Field>
        <Field label={t("guests.warningNote")} hint={t("guests.warningHint")} className="col-span-2">
          <TextInput autoFocus={focusNote} value={f.warning_note} onChange={(e) => set({ warning_note: e.target.value })} />
        </Field>
      </div>
      <div className="flex flex-col gap-2">
        <span className="text-label text-text-secondary">{t("newRes.companions")}</span>
        {f.companions.map((c, i) => (
          <div key={i} className="grid grid-cols-[2fr_1fr_36px] gap-3">
            <TextInput aria-label={t("newRes.companionName")} value={c.name} onChange={(e) => set({ companions: f.companions.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)) })} />
            <TextInput aria-label={t("newRes.relation")} value={c.relation} onChange={(e) => set({ companions: f.companions.map((x, j) => (j === i ? { ...x, relation: e.target.value } : x)) })} />
            <button type="button" aria-label={t("newRes.removeCompanion")} onClick={() => set({ companions: f.companions.filter((_, j) => j !== i) })} className="flex h-9 w-9 items-center justify-center rounded-control border border-border-strong bg-bg-surface text-text-secondary">
              <X className="h-icon-inline w-icon-inline" strokeWidth={1.75} aria-hidden />
            </button>
          </div>
        ))}
        <button type="button" onClick={() => set({ companions: [...f.companions, { name: "", relation: "" }] })} className="inline-flex w-fit items-center gap-1.5 border-0 bg-transparent p-0 font-sans text-body font-medium text-primary">
          <Plus className="h-icon-inline w-icon-inline" strokeWidth={1.75} aria-hidden />
          {t("newRes.addCompanion")}
        </button>
      </div>
      {error && <ErrorBanner>{error}</ErrorBanner>}
    </Modal>
  );
}
