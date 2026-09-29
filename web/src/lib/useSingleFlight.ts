import { useRef } from "react";

/** One save at a time. A second Enter pressed before the first answer came back is ignored: state updates too late
 *  to stop it, so a payment was recorded twice 31 ms apart (review 2026-09-28, UI-1). */
export function useSingleFlight() {
  const running = useRef(false);
  return async <T>(run: () => Promise<T>): Promise<T | undefined> => {
    if (running.current) return undefined;
    running.current = true;
    try {
      return await run();
    } finally {
      running.current = false;
    }
  };
}
