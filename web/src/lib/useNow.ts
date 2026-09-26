import { useEffect, useState } from "react";

/** Current time, refreshed every `intervalMs` (countdowns, «منذ …» labels, clocks). */
export function useNow(intervalMs: number): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
  return now;
}
