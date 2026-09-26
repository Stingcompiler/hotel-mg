import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, LogIn } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useBlocker, useNavigate, useSearchParams } from "react-router-dom";

import { api, ApiError, data } from "@/api/client";
import { keys, useSystemStatus } from "@/api/queries";
import { ErrorBanner, Section } from "@/components/ui/form";
import { useRoomBoard } from "@/features/rooms/RoomBoardPage";
import { formatRange } from "@/i18n/dates";
import { digits } from "@/i18n/digits";
import { formatMoney } from "@/i18n/money";
import { t } from "@/i18n/t";
import { notice } from "@/lib/notices";

import { GuestSection } from "./GuestSection";
import { amount, emptyForm, type Errors, errorSummary, type Form, guestReady, validate } from "./model";
import { MoneySection } from "./MoneySection";
import { StaySection, useRoomTypes } from "./StaySection";

const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

/** 6.4 New reservation / walk-in check-in: guest → stay → money, totals bar fixed at the bottom. */
export function NewReservationPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [params] = useSearchParams();
  const offline = useSystemStatus().isError;
  const board = useRoomBoard().data;
  const roomTypes = useRoomTypes().data ?? [];
  const [form, setForm] = useState<Form>(() => emptyForm(board?.date ?? todayIso()));
  const [errors, setErrors] = useState<Errors>({});
  const [banner, setBanner] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const update = (patch: Partial<Form>) => setForm((f) => ({ ...f, ...patch }));
  // «تغييرات غير محفوظة»: the form against its baseline (empty, or the presets from the URL); leaving asks first.
  const [baseline, setBaseline] = useState<Form>(() => emptyForm(board?.date ?? todayIso()));
  const saved = useRef(false);
  const dirty = useRef(false);
  dirty.current = !saved.current && JSON.stringify(form) !== JSON.stringify(baseline);
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty.current && currentLocation.pathname !== nextLocation.pathname);
  useEffect(() => {
    if (blocker.state !== "blocked") return;
    if (window.confirm(t("newRes.unsaved"))) blocker.proceed();
    else blocker.reset();
  }, [blocker]);
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (!dirty.current) return;
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, []);

  // From the room drawer («حجز جديد لهذه الغرفة») or a timeline cell: the room, its type and — from the cell — the day.
  const preset = params.get("room");
  const presetDate = params.get("date");
  useEffect(() => {
    const room = preset && board?.rooms.find((r) => r.id === preset);
    const date = presetDate && board && presetDate >= board.date ? presetDate : board?.date;
    if (room && !form.room_type) {
      update({ room_type: room.room_type, room: room.id, check_in_date: date! });
      setBaseline((b) => ({ ...b, room_type: room.room_type, room: room.id, check_in_date: date! }));
    }
  }, [preset, presetDate, board]);

  // From the guest profile: «حجز جديد لهذا النزيل».
  const presetGuest = params.get("guest");
  const guestRow = useQuery({
    queryKey: ["guests", "row", presetGuest],
    queryFn: () => data(api.GET("/api/v1/guests/{id}", { params: { path: { id: presetGuest! } } })),
    enabled: !!presetGuest,
  }).data;
  useEffect(() => {
    if (guestRow && form.guestMode !== "picked") {
      const picked = { ...guestRow, stays_count: 0, last_stay: null, debt: 0, in_house: false };
      update({ guestMode: "picked", picked });
      setBaseline((b) => ({ ...b, guestMode: "picked", picked }));
    }
  }, [guestRow]);

  const quote = useQuery({
    queryKey: ["quote", form.room_type, form.check_in_date, form.duration_kind, form.count],
    queryFn: () =>
      data(
        api.POST("/api/v1/reservations/quote", {
          body: { room_type: form.room_type, check_in_date: form.check_in_date, duration_kind: form.duration_kind, count: form.count },
        }),
      ),
    enabled: !!form.room_type && !!form.check_in_date,
    retry: false,
  });

  const option = quote.data?.options.find((o) => o.key === form.option_key) ?? quote.data?.options[0];
  const type = roomTypes.find((rt) => rt.id === form.room_type);
  const planPrice = option?.total ?? 0;
  const price = form.price !== null ? amount(form.price) ?? planPrice : planPrice;
  const discount = amount(form.discount) ?? 0;
  const deposit = amount(form.deposit) ?? 0;
  const total = price - discount;
  const roomNumber = board?.rooms.find((r) => r.id === form.room)?.number;
  const isToday = form.check_in_date === (board?.date ?? todayIso());
  const stayOpen = guestReady(form);
  const priced = stayOpen && !!quote.data && !!option;

  const summary = useMemo(() => {
    if (!quote.data || !type || !option) return "";
    const vars = {
      room: digits(roomNumber ?? ""),
      type: type.name,
      kind: option.label,
      range: formatRange(quote.data.check_in_date, quote.data.last_night),
    };
    return roomNumber ? t("newRes.summary", vars) : t("newRes.summaryNoRoom", vars);
  }, [quote.data, type, option, roomNumber]);

  async function save(checkInNow: boolean) {
    const problems = validate(form, checkInNow);
    setErrors(problems);
    if (Object.keys(problems).length) return setBanner(errorSummary(problems));
    setBanner(null);
    setSaving(true);
    try {
      let guestId = form.picked?.id;
      if (!guestId) {
        const g = form.guest;
        const created = await data(
          api.POST("/api/v1/guests/", {
            body: {
              full_name: g.full_name.trim(),
              phone: g.phone.trim(),
              nationality: g.nationality.trim(),
              id_type: g.id_type,
              id_number: g.id_number.trim(),
              companions: g.companions.filter((c) => c.name.trim()),
            },
          }),
        );
        guestId = created.id;
        // Keep it as the picked guest so a failed booking below does not register them twice.
        update({ guestMode: "picked", picked: { ...created, stays_count: 0, last_stay: null, debt: 0, in_house: false } });
        if (g.photo) {
          const body = new FormData();
          body.append("file", g.photo);
          try {
            await api.POST("/api/v1/guests/{id}/documents", {
              params: { path: { id: guestId } },
              body: body as never,
              bodySerializer: (b: unknown) => b as FormData,
            });
          } catch (e) {
            setBanner(t("newRes.photoFailed", { error: e instanceof ApiError ? e.message : "" }));
          }
        }
      }
      const reservation = await data(
        api.POST("/api/v1/reservations/", {
          body: {
            guest: guestId,
            room_type: form.room_type,
            room: form.room,
            check_in_date: form.check_in_date,
            duration_kind: form.duration_kind,
            count: form.count,
            option_key: option?.key ?? null,
            final_total: form.price !== null ? price : null,
            override_reason: form.override_reason.trim(),
            check_in_now: checkInNow,
            discount,
            discount_reason: form.discount_reason.trim(),
            deposit,
            deposit_method: form.deposit_method,
            deposit_reference: form.deposit_reference.trim(),
            manager_password: form.manager_password,
            manager_reason: form.manager_reason.trim(),
          },
        }),
      );
      void queryClient.invalidateQueries({ queryKey: keys.roomBoard });
      void queryClient.invalidateQueries({ queryKey: keys.currentShift });
      void queryClient.invalidateQueries({ queryKey: ["reservations"] });
      void queryClient.invalidateQueries({ queryKey: ["guests"] });
      saved.current = true;
      dirty.current = false;
      notice(checkInNow ? t("newRes.savedCheckIn") : t("newRes.savedBooking"));
      navigate(checkInNow ? "/" : `/reservations?focus=${reservation.id}`);
    } catch (e) {
      if (e instanceof ApiError && e.code === "override_required") update({ needManager: true });
      setBanner(e instanceof ApiError ? e.message : t("errors.error"));
    } finally {
      setSaving(false);
    }
  }

  const canSave = priced && !saving && !offline;
  const money = (v: number) => (priced ? formatMoney(v) : "—");

  return (
    <div className="flex h-full flex-col">
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto px-6 pt-6">
        <div className="flex h-9 items-center gap-3">
          <Link to="/reservations" className="inline-flex items-center gap-1 text-body text-text-secondary">
            {/* «رجوع» points to the start (right) in RTL (RTL notes «الأيقونات والنص»). */}
            <ChevronRight className="h-icon-inline w-icon-inline" strokeWidth={1.75} aria-hidden />
            {t("newRes.back")}
          </Link>
          <h1 className="m-0 text-page-title">{t("newRes.title")}</h1>
        </div>
        <div className="flex max-w-[1240px] flex-col gap-3 pb-6">
          {banner && <ErrorBanner>{banner}</ErrorBanner>}
          <GuestSection form={form} errors={errors} update={update} />
          {stayOpen ? (
            <StaySection form={form} errors={errors} update={update} quote={quote.data} quoteLoading={quote.isFetching} />
          ) : (
            <Section step={2} title={t("newRes.stay")} note={t("newRes.stayClosed")} />
          )}
          {priced ? (
            <MoneySection
              form={form}
              errors={errors}
              update={update}
              planPrice={planPrice}
              planLabel={t("newRes.fromPlan", { type: type?.name ?? "", kind: option!.label })}
            />
          ) : (
            <Section step={3} title={t("newRes.money")} note={t("newRes.moneyClosed")} />
          )}
          {quote.isError && <ErrorBanner>{(quote.error as Error).message}</ErrorBanner>}
        </div>
      </div>

      <div className="flex h-[72px] flex-none items-center gap-8 border-t border-border bg-bg-surface px-6 shadow-elevated">
        <Total label={t("newRes.total")} value={money(total)} />
        <Total label={t("newRes.paid")} value={money(deposit)} />
        <div className="flex flex-col">
          <span className="text-label text-text-secondary">{t("newRes.remaining")}</span>
          <span className={`text-headline-number ${priced && total - deposit > 0 ? "text-danger" : ""}`}>
            {money(total - deposit)} {priced && <span className="text-[16px] font-semibold">{t("money.currency")}</span>}
          </span>
        </div>
        <div className="flex-1" />
        {summary && <div className="truncate text-body text-text-secondary">{summary}</div>}
        <button
          type="button"
          disabled={!canSave}
          onClick={() => void save(false)}
          className="inline-flex h-11 flex-none items-center gap-2 rounded-control border border-border-strong bg-bg-surface px-6 font-sans text-body font-semibold text-text-primary hover:bg-bg-surface-2 disabled:text-text-disabled"
        >
          {t("newRes.saveBooking")}
        </button>
        <button
          type="button"
          disabled={!canSave || !isToday}
          title={!isToday ? t("newRes.checkInOnlyToday") : undefined}
          onClick={() => void save(true)}
          className="inline-flex h-11 flex-none items-center gap-2 rounded-control border-0 bg-primary px-6 font-sans text-body font-semibold text-primary-text-on hover:bg-primary-hover disabled:bg-bg-surface-2 disabled:text-text-disabled"
        >
          <LogIn className="h-icon w-icon" strokeWidth={1.75} aria-hidden />
          {saving ? t("newRes.saving") : t("newRes.checkInNow")}
        </button>
      </div>
    </div>
  );
}

function Total({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-label text-text-secondary">{label}</span>
      <span className="text-page-title">
        {value} {value !== "—" && <span className="text-body font-medium text-text-secondary">{t("money.currency")}</span>}
      </span>
    </div>
  );
}
