/**
 * The Tauri desktop shell (spec §11) exposes `window.__TAURI__` to the SPA served by the local service.
 * In a normal browser (development) every call here is a no-op.
 */
type Unlisten = () => void;
type TauriGlobal = {
  notification?: {
    isPermissionGranted: () => Promise<boolean>;
    requestPermission: () => Promise<string>;
    sendNotification: (options: { title: string; body?: string }) => void;
  };
  event?: { listen: (name: string, handler: () => void) => Promise<Unlisten> };
};

function tauri(): TauriGlobal | null {
  return (window as unknown as { __TAURI__?: TauriGlobal }).__TAURI__ ?? null;
}

export const isDesktop = () => tauri() !== null;

/** Native Windows notification; works while the window is hidden in the tray. */
export async function notify(title: string, body?: string): Promise<void> {
  const api = tauri()?.notification;
  if (!api) return;
  let allowed = await api.isPermissionGranted();
  if (!allowed) allowed = (await api.requestPermission()) === "granted";
  if (allowed) api.sendNotification({ title, body });
}

/** Tray menu «نسخة احتياطية الآن»: the signed-in page runs the backup with its session. */
export function onTrayBackup(handler: () => void): Unlisten {
  const listen = tauri()?.event?.listen;
  if (!listen) return () => {};
  let stop: Unlisten | null = null;
  let cancelled = false;
  void listen("tray-backup", handler).then((unlisten) => {
    if (cancelled) unlisten();
    else stop = unlisten;
  });
  return () => {
    cancelled = true;
    stop?.();
  };
}
