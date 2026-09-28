import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";

import { MoneyInput } from "./form";

function Harness() {
  const [value, setValue] = useState("");
  return <MoneyInput aria-label="المبلغ" value={value} onChange={(e) => setValue(e.target.value)} />;
}

test("amounts are grouped by thousands as they are typed, Arabic digits included", () => {
  render(<Harness />);
  const input = screen.getByLabelText("المبلغ") as HTMLInputElement;
  fireEvent.change(input, { target: { value: "1500000" } });
  expect(input.value).toBe("1,500,000");
  fireEvent.change(input, { target: { value: "١٠٠٠٠٠٠٠٠" } });
  expect(input.value).toBe("100,000,000");
  fireEvent.change(input, { target: { value: "2500.5" } });
  expect(input.value).toBe("2,500.5");
  fireEvent.change(input, { target: { value: "-50" } }); // not a plain amount: left for validation
  expect(input.value).toBe("-50");
});
