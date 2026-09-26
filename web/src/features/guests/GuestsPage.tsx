import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, EyeOff, ImageUp, Search, TriangleAlert, UserPlus } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import type { components } from "@api/schema";

import { api, data } from "@/api/client";
import { useMe, useSystemStatus } from "@/api/queries";
import { session } from "@/api/session";
import { Segmented } from "@/components/ui/form";
import { buttons } from "@/components/ui/Modal";
import { stateColor } from "@/design/state";
import { nights, staysCount } from "@/i18n/counts";
import { formatDate, formatDayMonth, formatMonthYear, formatRange } from "@/i18n/dates";
import { digits } from "@/i18n/digits";
import { formatMoney } from "@/i18n/money";
import { t } from "@/i18n/t";

import { GuestFormModal } from "./GuestForm";

type Filter = "all" | "debt" | "warning" | "in_house";
type Guest = components["schemas"]["Guest"];

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(id);
  }, [value, ms]);
  return v;
}

const guestList = (query: Record<string, string | number>) =>
  data(api.GET("/api/v1/guests/", { params: { query: query as never } }));

/** 6.9 Guests: list with filters on the start side, the guest profile panel (520 px) on the end side. */
export function GuestsPage() {
  const offline = useSystemStatus().isError;
  const queryClient = useQueryClient();
  // The top-bar search lands here with `?q=…&select=<guest id>`.
  const [params] = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const term = useDebounced(q.trim(), 250);
  const [filter, setFilter] = useState<Filter>("all");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string | null>(params.get("select"));
  const [form, setForm] = useState<null | { guest?: Guest; note?: boolean }>(null);
  useEffect(() => setPage(1), [term, filter]);
  useEffect(() => {
    const id = params.get("select");
    if (id) {
      setSelected(id);
      setQ(params.get("q") ?? "");
    }
  }, [params]);
  // The owner PC only reads (spec §10.4): no new guest, edit, note or booking there.
  const canWrite = session.role !== "owner";

  const query = { ...(term ? { q: term } : {}), ...(filter !== "all" ? { [filter === "warning" ? "warning" : filter]: 1 } : {}), page };
  const list = useQuery({ queryKey: ["guests", "list", query], queryFn: () => guestList(query) });
  const debtCount = useQuery({ queryKey: ["guests", "count", "debt"], queryFn: () => guestList({ debt: 1 }) }).data?.count;
  const warnCount = useQuery({ queryKey: ["guests", "count", "warning"], queryFn: () => guestList({ warning: 1 }) }).data?.count;
  const allCount = useQuery({ queryKey: ["guests", "count", "all"], queryFn: () => guestList({}) }).data?.count;
  const rows = list.data?.results ?? [];
  const GRID = "grid grid-cols-[1.6fr_170px_110px_110px_130px_140px] items-center gap-3 px-4";

  return (
    <div className="grid h-full grid-cols-[1fr_520px] grid-rows-[36px_1fr] gap-4 p-6 max-[1599px]:grid-cols-[1fr_440px] max-[1599px]:gap-3">
      <div className="col-span-2 flex items-center gap-3">
        <h1 className="m-0 text-page-title">{t("guests.title")}</h1>
        {allCount !== undefined && <span className="text-body text-text-secondary">{t("guests.total", { n: digits(String(allCount)) })}</span>}
        <span className="flex h-9 w-[360px] items-center gap-2 rounded-control border border-border-strong bg-bg-surface px-3 focus-within:border-primary max-[1599px]:w-64">
          <Search className="h-icon w-icon flex-none text-text-secondary" strokeWidth={1.75} aria-hidden />
          <input
            value={q}
            aria-label={t("guests.search")}
            placeholder={t("guests.search")}
            onChange={(e) => setQ(e.target.value)}
            className="w-full border-0 bg-transparent p-0 font-sans text-body text-text-primary outline-none placeholder:text-text-disabled"
          />
        </span>
        <Segmented<Filter>
          label={t("guests.title")}
          value={filter}
          onChange={setFilter}
          options={[
            { value: "all", label: t("guests.all") },
            { value: "debt", label: `${t("guests.debt")} ${debtCount ? digits(String(debtCount)) : ""}`.trim() },
            { value: "warning", label: `${t("guests.warning")} ${warnCount ? digits(String(warnCount)) : ""}`.trim() },
            { value: "in_house", label: t("guests.inHouse") },
          ]}
        />
        <div className="flex-1" />
        {canWrite && (
          <button type="button" disabled={offline} title={offline ? t("common.offlineHint") : undefined} onClick={() => setForm({})} className={`${buttons.secondary} h-9 px-4`}>
            <UserPlus className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
            {t("guests.new")}
          </button>
        )}
      </div>

      <section className="flex min-h-0 flex-col overflow-hidden rounded-card border border-border bg-bg-surface">
        <div className={`${GRID} h-10 flex-none bg-bg-surface-2 text-label text-text-secondary`}>
          {["colName", "colPhone", "colNationality", "colStays", "colLast", "colDebt"].map((k) => (
            <div key={k} className={k === "colDebt" ? "text-end" : ""}>
              {t(`guests.${k}`)}
            </div>
          ))}
        </div>
        <div className="min-h-0 flex-1 overflow-auto">
          {list.isSuccess && rows.length === 0 && <div className="p-6 text-center text-body text-text-secondary">{t("guests.empty")}</div>}
          {rows.map((g) => (
            <button
              key={g.id}
              type="button"
              onClick={() => setSelected(g.id)}
              className={`${GRID} h-10 w-full border-0 border-b border-border text-start font-sans text-table-cell text-text-primary ${
                selected === g.id ? "bg-primary-soft" : "bg-bg-surface hover:bg-bg-page"
              }`}
            >
              <span className="flex min-w-0 items-center gap-2">
                <span className={`truncate ${selected === g.id ? "font-semibold" : ""}`}>{g.full_name}</span>
                {g.warning_note && <TriangleAlert className="h-icon-inline w-icon-inline flex-none text-warning" strokeWidth={1.75} aria-label={t("guests.warningTitle")} />}
              </span>
              <span dir="ltr" className="text-end text-text-secondary">
                {g.phone}
              </span>
              <span>{g.nationality}</span>
              <span>{digits(String(g.stays_count))}</span>
              <span className="text-label font-normal text-text-secondary">
                {g.last_stay ? `${formatDayMonth(g.last_stay.check_in_date)} · ${digits(g.last_stay.room)}` : "—"}
              </span>
              <span className={`text-end font-semibold ${g.debt > 0 ? "text-danger" : "text-text-disabled"}`}>{g.debt > 0 ? formatMoney(g.debt) : "—"}</span>
            </button>
          ))}
        </div>
        <div className="flex h-10 flex-none items-center justify-between border-t border-border px-4 text-label font-normal text-text-secondary">
          <span>
            {term
              ? t("guests.results", { n: digits(String(list.data?.count ?? 0)), q: term })
              : t("guests.count", { n: digits(String(list.data?.count ?? 0)) })}
          </span>
          <span className="flex items-center gap-3">
            <button type="button" disabled={!list.data?.previous} onClick={() => setPage((p) => p - 1)} className="border-0 bg-transparent font-sans text-label text-primary disabled:text-text-disabled">
              {t("guests.prev")}
            </button>
            {t("guests.page", { n: digits(String(page)) })}
            <button type="button" disabled={!list.data?.next} onClick={() => setPage((p) => p + 1)} className="border-0 bg-transparent font-sans text-label text-primary disabled:text-text-disabled">
              {t("guests.next")}
            </button>
          </span>
        </div>
      </section>

      <aside className="flex min-h-0 flex-col overflow-hidden rounded-card border border-border bg-bg-surface">
        {selected ? (
          <GuestProfile id={selected} offline={offline} canWrite={canWrite} onEdit={(guest, note) => setForm({ guest, note })} />
        ) : (
          <div className="flex flex-1 items-center justify-center p-8 text-center text-body text-text-secondary">{t("guests.pick")}</div>
        )}
      </aside>

      {form && (
        <GuestFormModal
          guest={form.guest}
          focusNote={form.note}
          onClose={() => setForm(null)}
          onDone={(id) => {
            setForm(null);
            setSelected(id);
            void queryClient.invalidateQueries({ queryKey: ["guests"] });
          }}
        />
      )}
    </div>
  );
}

function GuestProfile({ id, offline, canWrite, onEdit }: { id: string; offline: boolean; canWrite: boolean; onEdit: (g: Guest, note?: boolean) => void }) {
  const navigate = useNavigate();
  const [tab, setTab] = useState<"stays" | "companions" | "id">("stays");
  const guest = useQuery({ queryKey: ["guests", id], queryFn: () => data(api.GET("/api/v1/guests/{id}", { params: { path: { id } } })) }).data;
  const history = useQuery({ queryKey: ["guests", id, "history"], queryFn: () => data(api.GET("/api/v1/guests/{id}/history", { params: { path: { id } } })) }).data;
  if (!guest || !history) return <div className="skeleton m-4 h-40 rounded-card" />;

  const stayed = history.filter((h) => h.status === "checked_in" || h.status === "checked_out");
  const debt = stayed.reduce((s, h) => s + Math.max(h.balance, 0), 0);
  const paid = history.reduce((s, h) => s + h.paid, 0);
  const current = history.find((h) => h.status === "checked_in");
  const occupied = stateColor("occupied");
  const companions = guest.companions as { name?: string; relation?: string }[];

  return (
    <>
      <div className="flex flex-col gap-3 border-b border-border px-5 py-4">
        <div className="flex items-start gap-3">
          <span className="flex h-12 w-12 flex-none items-center justify-center rounded-full bg-primary-soft text-section-title text-primary">{guest.full_name.charAt(0)}</span>
          <div className="min-w-0 flex-1">
            <div className="text-section-title">{guest.full_name}</div>
            <div className="text-body text-text-secondary">
              {[guest.phone && <span key="p" dir="ltr">{guest.phone}</span>, guest.nationality, guest.id_type && `${t(`idType.${guest.id_type}`)} `]
                .filter(Boolean)
                .flatMap((x, i) => (i ? [" · ", x] : [x]))}
              {guest.id_number && <span dir="ltr">{guest.id_number}</span>}
            </div>
            <div className="text-label font-normal text-text-secondary">
              {t("guests.since", {
                date: formatMonthYear(guest.created_at),
                stays: staysCount(stayed.length),
                nights: nights(stayed.reduce((s, h) => s + h.nights, 0)),
              })}
            </div>
          </div>
          {canWrite && (
            <button type="button" disabled={offline} onClick={() => onEdit(guest)} className={`${buttons.secondary} h-9 px-3 text-label`}>
              {t("guests.edit")}
            </button>
          )}
        </div>
        {guest.warning_note && (
          <div className="flex gap-3 rounded-control bg-warning-soft px-3 py-2.5 text-warning-text">
            <TriangleAlert className="mt-0.5 h-icon w-icon flex-none" strokeWidth={1.75} aria-hidden />
            <div className="flex-1 text-body">
              <div className="font-semibold">{t("guests.warningTitle")}</div>
              <div>{guest.warning_note}</div>
            </div>
          </div>
        )}
        <div className="grid grid-cols-3 gap-2">
          <div className="rounded-control border border-border px-3 py-2">
            <div className="text-label text-text-secondary">{t("guests.kDebt")}</div>
            <div className={`text-page-title font-bold ${debt > 0 ? "text-danger" : ""}`}>{formatMoney(debt)}</div>
          </div>
          <div className="rounded-control border border-border px-3 py-2">
            <div className="text-label text-text-secondary">{t("guests.kPaid")}</div>
            <div className="text-page-title font-bold">{formatMoney(paid)}</div>
          </div>
          <div className="rounded-control border border-border px-3 py-2">
            <div className="text-label text-text-secondary">{t("guests.kState")}</div>
            {current ? (
              <span className={`inline-flex h-6 items-center rounded-control px-2 text-label ${occupied.soft} ${occupied.text}`}>
                {t("guests.inHouseAt", { room: digits(current.room ?? "") })}
              </span>
            ) : (
              <span className="text-label text-text-secondary">{t("guests.notInHouse")}</span>
            )}
          </div>
        </div>
      </div>

      <div role="tablist" className="flex flex-none items-center gap-1 border-b border-border px-3">
        {(["stays", "companions", "id"] as const).map((k) => (
          <button
            key={k}
            type="button"
            role="tab"
            aria-selected={tab === k}
            onClick={() => setTab(k)}
            className={`-mb-px inline-flex h-11 items-center border-0 border-b-2 bg-transparent px-3 font-sans text-body ${tab === k ? "border-primary font-semibold text-primary" : "border-transparent text-text-secondary"}`}
          >
            {t(k === "stays" ? "guests.tabStays" : k === "companions" ? "guests.tabCompanions" : "guests.tabId")}
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        {tab === "stays" &&
          (history.length ? (
            history.map((h) => {
              const row = (
                <>
                  <span className="text-section-title">{digits(h.room ?? "—")}</span>
                  <div className="min-w-0">
                    <div className="text-body font-medium">{formatRange(h.check_in_date, h.last_night)}</div>
                    <div className="text-label font-normal text-text-secondary">
                      {t("guests.stayMeta", { nights: nights(h.nights), kind: h.duration_label, status: h.status_label })}
                    </div>
                  </div>
                  <div className="text-end">
                    <div className={`text-body font-semibold ${h.balance > 0 ? "text-danger" : "text-text-primary"}`}>{formatMoney(h.balance)}</div>
                    <div className="text-label font-normal text-text-secondary">{t("guests.ofTotal", { total: formatMoney(h.total) })}</div>
                  </div>
                  <ChevronLeft className="h-icon-inline w-icon-inline text-text-secondary" strokeWidth={1.75} aria-hidden />
                </>
              );
              const cls = "grid grid-cols-[64px_1fr_auto_16px] items-center gap-3 border-b border-border px-5 py-3 text-text-primary hover:bg-bg-page";
              return h.stay ? (
                <Link key={h.reservation_id} to={`/stays/${h.stay}`} className={`${cls} hover:text-text-primary`}>
                  {row}
                </Link>
              ) : (
                <div key={h.reservation_id} className={cls}>
                  {row}
                </div>
              );
            })
          ) : (
            <div className="p-6 text-center text-body text-text-secondary">{t("guests.noStays")}</div>
          ))}
        {tab === "companions" &&
          (companions.length ? (
            companions.map((c, i) => (
              <div key={i} className="flex h-10 items-center gap-4 border-b border-border px-5 text-table-cell">
                <span className="font-medium">{c.name}</span>
                <span className="text-text-secondary">{c.relation}</span>
              </div>
            ))
          ) : (
            <div className="p-6 text-center text-body text-text-secondary">{t("guests.noCompanions")}</div>
          ))}
        {tab === "id" && <IdTab guest={guest} offline={offline} />}
      </div>

      {canWrite && (
        <div className="flex flex-none gap-2 border-t border-border px-5 py-3">
          <button type="button" disabled={offline} onClick={() => navigate(`/reservations/new?guest=${guest.id}`)} className={`${buttons.primary} h-9 px-4`}>
            {t("guests.newBooking")}
          </button>
          <button type="button" disabled={offline} onClick={() => onEdit(guest, true)} className={`${buttons.secondary} h-9 px-3`}>
            {t("guests.addNote")}
          </button>
        </div>
      )}
    </>
  );
}

/** Gap Fill 6.9: the ID image is blurred by default; viewing it needs a manager and is audited by the server. */
function IdTab({ guest, offline }: { guest: Guest; offline: boolean }) {
  const queryClient = useQueryClient();
  const me = useMe().data;
  const isManager = me?.role === "manager" || me?.role === "owner";
  const doc = guest.documents[0];
  const [url, setUrl] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => () => void (url && URL.revokeObjectURL(url)), [url]);

  const view = async () => {
    const res = await fetch(`${window.location.origin}/api/v1/guests/${guest.id}/documents/${doc.id}`, { headers: { Authorization: `Token ${session.token}` } });
    if (res.ok) setUrl(URL.createObjectURL(await res.blob()));
  };
  const uploadFile = async (file: File) => {
    const body = new FormData();
    body.append("file", file);
    await api.POST("/api/v1/guests/{id}/documents", { params: { path: { id: guest.id } }, body: body as never, bodySerializer: (b: unknown) => b as FormData });
    void queryClient.invalidateQueries({ queryKey: ["guests", guest.id] });
  };

  return (
    <div className="flex flex-col gap-3 px-5 py-4">
      <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-body">
        <div>
          <div className="text-label font-normal text-text-secondary">{t("guests.idType")}</div>
          <div>{guest.id_type ? t(`idType.${guest.id_type}`) : "—"}</div>
        </div>
        <div>
          <div className="text-label font-normal text-text-secondary">{t("guests.idNumber")}</div>
          <div dir="ltr" className="text-end">
            {guest.id_number || "—"}
          </div>
        </div>
        <div>
          <div className="text-label font-normal text-text-secondary">{t("guests.nationality")}</div>
          <div>{guest.nationality || "—"}</div>
        </div>
        {doc && (
          <div>
            <div className="text-label font-normal text-text-secondary">{t("guests.added")}</div>
            <div>
              {formatDate(doc.created_at)}
              {doc.added_by ? ` · ${doc.added_by}` : ""}
            </div>
          </div>
        )}
      </div>
      {doc ? (
        <div className="relative flex h-[200px] items-center justify-center overflow-hidden rounded-control border border-border bg-bg-surface-2">
          {url ? (
            <>
              <img src={url} alt={t("guests.tabId")} className="h-full w-full object-contain" />
              <button type="button" onClick={() => setUrl(null)} className={`${buttons.secondary} absolute bottom-2 end-2 h-8 px-3`}>
                {t("guests.hide")}
              </button>
            </>
          ) : (
            <div className="flex flex-col items-center gap-2 text-center">
              <EyeOff className="h-8 w-8 text-text-secondary" strokeWidth={1.75} aria-hidden />
              <div className="text-body text-text-secondary">{t("guests.blurred")}</div>
              <button type="button" disabled={!isManager || offline} onClick={() => void view()} className={`${buttons.secondary} h-9 px-3`}>
                {t("guests.view")}
              </button>
            </div>
          )}
        </div>
      ) : (
        <button type="button" disabled={offline || session.role === "owner"} onClick={() => input.current?.click()} className="flex h-16 items-center justify-center gap-2 rounded-control border border-dashed border-border-strong bg-bg-page font-sans text-body text-text-secondary disabled:text-text-disabled">
          <ImageUp className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
          {t("guests.upload")}
        </button>
      )}
      <input ref={input} type="file" accept="image/*" className="sr-only" onChange={(e) => e.target.files?.[0] && void uploadFile(e.target.files[0])} />
      <div className="text-label font-normal text-text-secondary">{t("guests.idNote")}</div>
    </div>
  );
}
