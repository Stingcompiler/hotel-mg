import { KeyRound } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { t } from "@/i18n/t";

const DISMISSED = "skytowers.defaultPasswordLater";

function dismissed(): boolean {
  try {
    return window.sessionStorage.getItem(DISMISSED) === "1";
  } catch {
    return false;
  }
}

/**
 * Signed in with the install's default owner password: a reminder under the top bar, never a gate (owner decision
 * 2026-09-27). «لاحقًا» hides it until the next sign-in; changing the password removes it for good.
 */
export function DefaultPasswordNotice() {
  const [hidden, setHidden] = useState(dismissed);
  if (hidden) return null;
  const later = () => {
    try {
      window.sessionStorage.setItem(DISMISSED, "1");
    } catch {
      // storage unavailable: hide for this page view
    }
    setHidden(true);
  };
  return (
    <div role="status" className="flex min-h-11 items-center gap-3 bg-warning-soft px-6 py-2 text-body font-medium text-warning-text">
      <KeyRound className="h-icon w-icon flex-none" strokeWidth={1.75} aria-hidden />
      <span className="flex-1">{t("account.defaultPassword")}</span>
      <Link to="/settings/users" className="font-semibold text-warning-text underline underline-offset-2">
        {t("account.changeNow")}
      </Link>
      <button type="button" onClick={later} className="border-0 bg-transparent font-sans text-body font-medium text-warning-text hover:underline">
        {t("account.later")}
      </button>
    </div>
  );
}
