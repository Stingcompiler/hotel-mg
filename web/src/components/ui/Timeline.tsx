import { type ReactNode, useEffect, useRef } from "react";

export type TimelineItem = { key: string; time: ReactNode; title: ReactNode; meta?: ReactNode; dot?: string };

/**
 * History as a timeline (owner redesign brief 2026-10-18, decision 229): one thin teal line, a dot per event, the time
 * as a chip. Items fade up once when they scroll into view (`.reveal` in index.css; still under reduced motion).
 */
export function Timeline({ items }: { items: TimelineItem[] }) {
  const list = useRef<HTMLOListElement>(null);
  useEffect(() => {
    const nodes = [...(list.current?.querySelectorAll<HTMLElement>(".reveal:not(.is-in)") ?? [])];
    if (typeof IntersectionObserver === "undefined") {
      nodes.forEach((n) => n.classList.add("is-in"));
      return;
    }
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (!e.isIntersecting) continue;
        e.target.classList.add("is-in");
        io.unobserve(e.target);
      }
    });
    nodes.forEach((n) => io.observe(n));
    return () => io.disconnect();
  }, [items]);

  return (
    <ol ref={list} className="relative m-0 flex list-none flex-col gap-4 p-0 ps-6">
      <span aria-hidden className="absolute bottom-2 start-[7px] top-2 w-px bg-primary opacity-30" />
      {items.map((item) => (
        <li key={item.key} className="reveal relative flex flex-col gap-1">
          <span aria-hidden className={`absolute -start-[21px] top-1 h-2.5 w-2.5 rounded-full ring-2 ring-bg-surface ${item.dot ?? "bg-primary"}`} />
          <span className="flex flex-wrap items-center gap-2">
            <span className="inline-flex h-6 items-center rounded-full bg-primary-soft px-2 text-label text-primary">{item.time}</span>
            <span className="text-body leading-5 text-text-primary">{item.title}</span>
          </span>
          {item.meta && <span className="text-label font-normal text-text-secondary">{item.meta}</span>}
        </li>
      ))}
    </ol>
  );
}
