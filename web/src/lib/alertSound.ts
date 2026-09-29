import { api } from "@/api/client";

/**
 * The alert sound (owner request 2026-09-28): the owner's own sound when one is saved, otherwise a built-in two-tone
 * chime made with Web Audio (no file to ship). Each PC may switch the sound off for itself.
 */
const MUTED = "skytowers.alertSoundOff";
let custom: { key: string; url: string } | null = null;

export function soundMuted(): boolean {
  try {
    return window.localStorage.getItem(MUTED) === "1";
  } catch {
    return false;
  }
}

export function setSoundMuted(muted: boolean): void {
  try {
    if (muted) window.localStorage.setItem(MUTED, "1");
    else window.localStorage.removeItem(MUTED);
  } catch {
    // storage unavailable: the choice lasts for this page view only
  }
}

/** The built-in tone: two soft notes, about half a second. */
export function playDefaultTone(): void {
  const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctx) return;
  const ctx = new Ctx();
  [880, 1320].forEach((frequency, i) => {
    const start = ctx.currentTime + i * 0.18;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = frequency;
    gain.gain.setValueAtTime(0.0001, start);
    gain.gain.exponentialRampToValueAtTime(0.25, start + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.3);
    osc.connect(gain).connect(ctx.destination);
    osc.start(start);
    osc.stop(start + 0.32);
  });
  window.setTimeout(() => void ctx.close(), 1000);
}

/** The owner's sound, fetched once per change (``version`` is its updated_at). */
async function customUrl(version: string): Promise<string | null> {
  if (custom?.key === version) return custom.url;
  const res = await api.GET("/api/v1/system/alert-sound", { parseAs: "blob" });
  if (!res.data) return null;
  if (custom) URL.revokeObjectURL(custom.url);
  custom = { key: version, url: URL.createObjectURL(res.data as Blob) };
  return custom.url;
}

/**
 * Play the alert once. ``version`` is the saved sound's updated_at, or null for the built-in tone.
 * ``force`` plays even when this PC switched the sound off (the «تجربة الصوت» button).
 */
export async function playAlert(version: string | null, force = false): Promise<void> {
  if (!force && soundMuted()) return;
  try {
    const url = version ? await customUrl(version) : null;
    if (url) {
      await new Audio(url).play();
      return;
    }
  } catch {
    // an unreadable or blocked file falls back to the built-in tone
  }
  try {
    playDefaultTone();
  } catch {
    // no audio device: stay silent
  }
}
