import ar from "./ar.json";

type Tree = { [key: string]: string | string[] | Tree };

/** Every UI string comes from ar.json (spec §10.1): `t("topbar.shiftOpen", { name, time })`. */
export function t(key: string, vars: Record<string, string | number> = {}): string {
  const value = key.split(".").reduce<string | string[] | Tree | undefined>(
    (node, part) => (node && typeof node === "object" && !Array.isArray(node) ? node[part] : undefined),
    ar as Tree,
  );
  if (typeof value !== "string") {
    if (import.meta.env.DEV) console.warn(`missing string: ${key}`);
    return key;
  }
  return value.replace(/\{(\w+)\}/g, (_, name: string) => String(vars[name] ?? `{${name}}`));
}

/** A list of words from ar.json (relations, nationalities, week days): `tList("lists.weekdays")`. No Arabic list
 *  lives in the code (review 2026-09-29, F-17). */
export function tList(key: string): string[] {
  const value = key.split(".").reduce<string | string[] | Tree | undefined>(
    (node, part) => (node && typeof node === "object" && !Array.isArray(node) ? node[part] : undefined),
    ar as Tree,
  );
  return Array.isArray(value) ? value : [];
}

/** Arabic message for an API error: the server's `detail` when present, else ar.json `errors.<code>`. */
export function errorMessage(code: string | undefined, detail?: string): string {
  if (detail) return detail;
  return t(`errors.${code && code in ar.errors ? code : "error"}`);
}
