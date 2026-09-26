import createClient, { type Middleware } from "openapi-fetch";

import type { paths } from "@api/schema";

import { errorMessage } from "@/i18n/t";

import { session } from "./session";

/** Error thrown for every non-2xx answer: stable `code`, Arabic `message`, and the server's extra fields. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly extra: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const CREDENTIAL_PATHS = ["/api/v1/auth/password", "/api/v1/auth/pin", "/api/v1/auth/confirm"];
const OWNER_WRITABLE = ["/api/v1/auth/", "/api/v1/owner/"];

const middleware: Middleware = {
  onRequest({ request }) {
    const method = request.method.toUpperCase();
    // Owner PC is read-only (spec §10.4); the server refuses too, this just fails fast without a round trip.
    if (session.role === "owner" && method !== "GET" && method !== "HEAD") {
      const path = new URL(request.url).pathname;
      if (!OWNER_WRITABLE.some((prefix) => path.startsWith(prefix))) {
        throw new ApiError(403, "owner_read_only", errorMessage("owner_read_only"));
      }
    }
    if (session.token) request.headers.set("Authorization", `Token ${session.token}`);
    return request;
  },
  async onResponse({ request, response }) {
    if (response.ok) return response;
    let body: Record<string, unknown> = {};
    try {
      body = await response.clone().json();
    } catch {
      // not JSON: the Django server did not answer (dev proxy error, gateway)
    }
    const code =
      typeof body.code === "string"
        ? body.code
        : response.status >= 500
          ? "server_unavailable"
          : "validation_error";
    const detail = typeof body.detail === "string" ? body.detail : undefined;
    // A wrong password on login or on the sensitive-action confirmation is not an expired session.
    const credentialsCheck = CREDENTIAL_PATHS.some((p) => new URL(request.url).pathname === p);
    if (response.status === 401 && !credentialsCheck) session.signOut();
    const { code: _code, detail: _detail, ...extra } = body;
    throw new ApiError(response.status, code, errorMessage(code, detail), extra);
  },
};

// Same origin as the page (Vite proxy in development, Django in production).
/** `fetch` resolved at call time; a refused connection becomes `server_unavailable` with its Arabic message. */
async function send(request: Request): Promise<Response> {
  try {
    return await globalThis.fetch(request);
  } catch {
    throw new ApiError(0, "server_unavailable", errorMessage("server_unavailable"));
  }
}

export const api = createClient<paths>({ baseUrl: window.location.origin, fetch: send });
api.use(middleware);

/** Unwraps an openapi-fetch result (errors were already thrown by the middleware). */
export async function data<T>(promise: Promise<{ data?: T }>): Promise<T> {
  const result = await promise;
  return result.data as T;
}

/** Downloads a file endpoint (report exports) with the session token; the server's filename is kept. */
export async function download(path: string, fallbackName: string): Promise<void> {
  let res: Response;
  try {
    res = await globalThis.fetch(`${window.location.origin}${path}`, { headers: session.token ? { Authorization: `Token ${session.token}` } : {} });
  } catch {
    throw new ApiError(0, "server_unavailable", errorMessage("server_unavailable"));
  }
  if (!res.ok) {
    let body: Record<string, unknown> = {};
    try {
      body = await res.json();
    } catch {
      // not JSON
    }
    const code = typeof body.code === "string" ? body.code : "error";
    throw new ApiError(res.status, code, errorMessage(code, typeof body.detail === "string" ? body.detail : undefined));
  }
  const blob = await res.blob();
  const name = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "")?.[1] ?? fallbackName;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}
