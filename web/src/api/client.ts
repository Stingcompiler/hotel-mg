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
  async onResponse({ response }) {
    if (response.ok) return response;
    let body: Record<string, unknown> = {};
    try {
      body = await response.clone().json();
    } catch {
      // not JSON (proxy error, server down)
    }
    const code = typeof body.code === "string" ? body.code : response.status >= 500 ? "error" : "validation_error";
    const detail = typeof body.detail === "string" ? body.detail : undefined;
    if (response.status === 401) session.signOut();
    const { code: _code, detail: _detail, ...extra } = body;
    throw new ApiError(response.status, code, errorMessage(code, detail), extra);
  },
};

// Same origin as the page (Vite proxy in development, Django in production).
export const api = createClient<paths>({ baseUrl: window.location.origin, fetch: (request) => globalThis.fetch(request) });
api.use(middleware);

/** Unwraps an openapi-fetch result (errors were already thrown by the middleware). */
export async function data<T>(promise: Promise<{ data?: T }>): Promise<T> {
  const result = await promise;
  return result.data as T;
}
