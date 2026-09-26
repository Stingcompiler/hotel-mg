import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";

import { Drawer } from "./Drawer";
import { Modal } from "./Modal";

function Host({ kind }: { kind: "modal" | "drawer" }) {
  const [open, setOpen] = useState(false);
  const body = (
    <>
      <input aria-label="المبلغ" />
      <input aria-label="البيان" />
    </>
  );
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        فتح
      </button>
      {open && kind === "modal" && (
        <Modal title="نافذة" onClose={() => setOpen(false)} footer={<button type="button">حفظ</button>}>
          {body}
        </Modal>
      )}
      {open && kind === "drawer" && (
        <Drawer title="درج" onClose={() => setOpen(false)}>
          {body}
        </Drawer>
      )}
    </>
  );
}

test.each(["modal", "drawer"] as const)("%s: first field focused, Tab stays inside, Esc closes and refocuses the opener", (kind) => {
  render(<Host kind={kind} />);
  const opener = screen.getByRole("button", { name: "فتح" });
  opener.focus();
  fireEvent.click(opener);
  const dialog = screen.getByRole("dialog");
  expect(dialog).toHaveAccessibleName(kind === "modal" ? "نافذة" : "درج");
  expect(document.activeElement).toBe(screen.getByRole("textbox", { name: "المبلغ" }));
  // Shift+Tab from the first field wraps to the last control of the dialog, never out of it.
  fireEvent.keyDown(window, { key: "Tab", shiftKey: true });
  expect(dialog.contains(document.activeElement)).toBe(true);
  fireEvent.keyDown(window, { key: "Escape" });
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(document.activeElement).toBe(opener);
});
