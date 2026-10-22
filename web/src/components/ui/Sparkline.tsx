/** Smooth path through the points (Catmull-Rom → cubic Bézier). Pure, so it is tested without a DOM. */
export function sparkPath(values: number[], width = 200, height = 44, pad = 4): string {
  if (values.length < 2) return "";
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const span = hi - lo || 1;
  const pts = values.map((v, i) => [2 + (i * (width - 4)) / (values.length - 1), pad + ((hi - v) / span) * (height - 2 * pad)] as const);
  const f = (n: number) => n.toFixed(1);
  let d = `M${f(pts[0][0])} ${f(pts[0][1])}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(i - 1, 0)];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[Math.min(i + 2, pts.length - 1)];
    d += ` C ${f(p1[0] + (p2[0] - p0[0]) / 6)} ${f(p1[1] + (p2[1] - p0[1]) / 6)}, ${f(p2[0] - (p3[0] - p1[0]) / 6)} ${f(p2[1] - (p3[1] - p1[1]) / 6)}, ${f(p2[0])} ${f(p2[1])}`;
  }
  return d;
}

/**
 * A bare trend line: no axes, no labels, a thin rounded teal stroke. The series is chronological and the latest point
 * is on the right, as in every chart here (RTL notes, «اتجاه الزمن»).
 */
export function Sparkline({ values, className = "" }: { values: number[]; className?: string }) {
  const d = sparkPath(values);
  if (!d) return null;
  return (
    <svg aria-hidden viewBox="0 0 200 44" preserveAspectRatio="none" className={`block h-11 w-full max-[1599px]:h-8 ${className}`}>
      <path d={d} fill="none" className="stroke-primary" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
