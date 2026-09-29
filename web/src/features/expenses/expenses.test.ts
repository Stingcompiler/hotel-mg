import { roomGroups } from "./ExpensesPage";

test("«مرتبط بغرفة» lists rooms by type with their name and floor", () => {
  const rooms = [
    { id: "a", number: "204", name: "", floor: 2, room_type_name: "مزدوجة" },
    { id: "b", number: "501", name: "الشقة العائلية", floor: 5, room_type_name: "شقة" },
    { id: "c", number: "205", name: "", floor: 2, room_type_name: "مزدوجة" },
  ];
  expect(roomGroups(rooms)).toEqual([
    { type: "مزدوجة", rooms: [{ id: "a", label: "204 · الطابق 2" }, { id: "c", label: "205 · الطابق 2" }] },
    { type: "شقة", rooms: [{ id: "b", label: "501 · الشقة العائلية · الطابق 5" }] },
  ]);
});
