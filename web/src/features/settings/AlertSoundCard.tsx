import { useQueryClient } from "@tanstack/react-query";
import { Play, RotateCcw, Upload } from "lucide-react";
import { useRef, useState } from "react";

import { api, data } from "@/api/client";
import { keys, useHotelSettings } from "@/api/queries";
import { ErrorBanner } from "@/components/ui/form";
import { Toggle } from "@/components/ui/Toggle";
import { t } from "@/i18n/t";
import { playAlert, setSoundMuted, soundMuted } from "@/lib/alertSound";

import { apiErrorText, Card, smallButton } from "./shared";

/** «صوت التنبيه»: the built-in tone unless the owner uploads a sound; each PC may switch it off for itself. */
export function AlertSoundCard({ readOnly, owner }: { readOnly: boolean; owner: boolean }) {
  const queryClient = useQueryClient();
  const sound = useHotelSettings().data?.alert_sound ?? null;
  const [on, setOn] = useState(() => !soundMuted());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const canEdit = owner && !readOnly;

  const refresh = () => void queryClient.invalidateQueries({ queryKey: keys.settings });
  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      refresh();
    } catch (e) {
      setError(apiErrorText(e));
    } finally {
      setBusy(false);
    }
  };
  const upload = (file: File) =>
    run(async () => {
      const body = new FormData();
      body.append("file", file);
      await data(api.POST("/api/v1/system/alert-sound", { body: body as never, bodySerializer: (b: unknown) => b as FormData }));
    });
  const reset = () => run(() => data(api.DELETE("/api/v1/system/alert-sound")));

  return (
    <Card title={t("settings.sound.title")} note={sound ? t("settings.sound.custom", { name: sound.name }) : t("settings.sound.default")}>
      <div className="flex flex-col gap-3 p-4">
        {error && <ErrorBanner>{error}</ErrorBanner>}
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={() => void playAlert(sound?.updated_at ?? null, true)} className={smallButton()}>
            <Play className="h-icon-inline w-icon-inline" strokeWidth={1.75} aria-hidden />
            {t("settings.sound.test")}
          </button>
          {canEdit && (
            <>
              <button type="button" disabled={busy} onClick={() => input.current?.click()} className={smallButton()}>
                <Upload className="h-icon-inline w-icon-inline" strokeWidth={1.75} aria-hidden />
                {t("settings.sound.upload")}
              </button>
              <input
                ref={input}
                type="file"
                accept="audio/mpeg,audio/wav,audio/ogg,.mp3,.wav,.ogg"
                className="sr-only"
                aria-label={t("settings.sound.upload")}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  e.target.value = "";
                  if (file) void upload(file);
                }}
              />
              {sound && (
                <button type="button" disabled={busy} onClick={() => void reset()} className={smallButton()}>
                  <RotateCcw className="h-icon-inline w-icon-inline" strokeWidth={1.75} aria-hidden />
                  {t("settings.sound.reset")}
                </button>
              )}
            </>
          )}
          <div className="flex-1" />
          <label className="flex items-center gap-2 text-body">
            <Toggle
              checked={on}
              label={t("settings.sound.onThisPc")}
              onChange={(next) => {
                setOn(next);
                setSoundMuted(!next);
              }}
            />
            {t("settings.sound.onThisPc")}
          </label>
        </div>
        <div className="text-label font-normal text-text-secondary">{owner ? t("settings.sound.hint") : t("settings.sound.ownerOnly")}</div>
      </div>
    </Card>
  );
}
