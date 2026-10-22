import { fireEvent, render, screen } from "@testing-library/react";
import { BedDouble } from "lucide-react";

import { Sparkline, sparkPath } from "./Sparkline";
import { StatCard } from "./StatCard";

test("a stat card shows the number, its label and the context line; nothing else without data", () => {
  const { container } = render(<StatCard icon={BedDouble} value="18" unit="٪" label="الإشغال اليوم" hint="60٪ إشغال" />);
  expect(screen.getByText("18")).toBeTruthy();
  expect(screen.getByText("الإشغال اليوم")).toBeTruthy();
  expect(screen.getByText("60٪ إشغال")).toBeTruthy();
  expect(container.querySelector("svg path[stroke-width]")).toBeNull(); // no series → no trend line
  expect(screen.queryByText(/[+−]/)).toBeNull(); // no comparison → no change pill
});

test("the change pill and the trend line appear only when the data is given", () => {
  const { container } = render(
    <StatCard icon={BedDouble} value="2" label="الإيراد" delta={{ text: "+٤٪", trend: "up" }} series={[1, 3, 2, 5]} />,
  );
  expect(screen.getByText("+٤٪")).toBeTruthy();
  expect(container.querySelector('path[stroke-width="2.5"]')).not.toBeNull();
});

test("a bad change reads red: debts rising is not good news", () => {
  render(<StatCard icon={BedDouble} value="2" label="الديون" delta={{ text: "+٩٪", trend: "up", good: false }} />);
  expect(screen.getByText("+٩٪").className).toContain("text-danger");
});

test("a card with a filter is a pressed-state button; a plain card is not interactive", () => {
  const onClick = vi.fn();
  const { rerender } = render(<StatCard icon={BedDouble} value="3" label="مشغولة" onClick={onClick} active />);
  const button = screen.getByRole("button");
  expect(button.getAttribute("aria-pressed")).toBe("true");
  fireEvent.click(button);
  expect(onClick).toHaveBeenCalledTimes(1);
  rerender(<StatCard icon={BedDouble} value="3" label="مشغولة" />);
  expect(screen.queryByRole("button")).toBeNull();
});

test("sparkPath is a smooth path through every point, highest value at the top, empty under two points", () => {
  expect(sparkPath([5])).toBe("");
  const d = sparkPath([10, 20, 15, 30]);
  expect(d.startsWith("M2.0 ")).toBe(true);
  expect(d.match(/ C /g)).toHaveLength(3); // one curve per segment
  const ys = [...d.matchAll(/, ([\d.]+) ([\d.]+)(?= C|$)/g)].map((m) => Number(m[2]));
  expect(Math.min(...ys)).toBeCloseTo(4, 0); // the maximum sits at the padding
  expect(sparkPath([2, 2, 2])).not.toContain("NaN"); // a flat series does not divide by zero
});

test("Sparkline renders nothing for a single point", () => {
  const { container } = render(<Sparkline values={[7]} />);
  expect(container.querySelector("svg")).toBeNull();
});
