/** The signed-in user's token and the device role. Token survives reloads; storage may be unavailable. */
const KEY = "skytowers.token";

type Listener = () => void;
const listeners = new Set<Listener>();

function read(): string | null {
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export const session = {
  token: read(),
  role: null as "reception" | "owner" | null,

  signIn(token: string) {
    this.token = token;
    try {
      window.localStorage.setItem(KEY, token);
    } catch {
      // private mode: keep it in memory only
    }
    listeners.forEach((l) => l());
  },

  signOut() {
    this.token = null;
    try {
      window.localStorage.removeItem(KEY);
    } catch {
      // ignore
    }
    listeners.forEach((l) => l());
  },

  subscribe(listener: Listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};
