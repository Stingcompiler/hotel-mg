import { useState } from "react";

import { useMediaQuery } from "@/lib/useMediaQuery";

const KEY = "skytowers.sidebar";

/** 1366×768 artboards fold the sidebar to the 64 px rail; a manual choice (remembered on this PC) wins over the width rule. */
export function useSidebar(): { collapsed: boolean; toggle: () => void } {
  const narrow = useMediaQuery("(max-width: 1599px)");
  const [manual, setManual] = useState<boolean | null>(() => {
    try {
      const v = localStorage.getItem(KEY);
      return v === null ? null : v === "collapsed";
    } catch {
      return null;
    }
  });
  const collapsed = manual ?? narrow;
  const toggle = () => {
    const next = !collapsed;
    setManual(next);
    try {
      localStorage.setItem(KEY, next ? "collapsed" : "open");
    } catch {
      /* private window or blocked storage: the choice lasts for this session only */
    }
  };
  return { collapsed, toggle };
}
