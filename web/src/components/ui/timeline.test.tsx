import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { Timeline } from "./Timeline";

test("each event shows its time chip, title and author, and is visible without an IntersectionObserver", () => {
  render(
    <Timeline
      items={[
        { key: "a", time: "18 أكتوبر · 15:37", title: "دفعة", meta: "المدير" },
        { key: "b", time: "18 أكتوبر · 15:30", title: "قيد إقامة" },
      ]}
    />,
  );
  expect(screen.getAllByRole("listitem")).toHaveLength(2);
  expect(screen.getByText("دفعة")).toBeTruthy();
  expect(screen.getByText("المدير")).toBeTruthy();
  for (const item of screen.getAllByRole("listitem")) expect(item.className).toContain("is-in");
});
