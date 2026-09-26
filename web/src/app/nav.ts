import {
  Bell,
  Calendar,
  ChartColumn,
  ChartLine,
  Download,
  LayoutGrid,
  type LucideIcon,
  Receipt,
  Settings,
  Users,
  Wallet,
} from "lucide-react";

export type NavKey =
  | "rooms"
  | "reservations"
  | "guests"
  | "followups"
  | "cash"
  | "expenses"
  | "reports"
  | "settings"
  | "owner"
  | "backup";

export type NavItem = { key: NavKey; path: string; icon: LucideIcon };

// Order and icons from «Shell Sidebar» (spec §10.4 routes).
export const RECEPTION_NAV: NavItem[] = [
  { key: "rooms", path: "/", icon: LayoutGrid },
  { key: "reservations", path: "/reservations", icon: Calendar },
  { key: "guests", path: "/guests", icon: Users },
  { key: "followups", path: "/followups", icon: Bell },
  { key: "cash", path: "/cash", icon: Wallet },
  { key: "expenses", path: "/expenses", icon: Receipt },
  { key: "reports", path: "/reports", icon: ChartColumn },
  { key: "settings", path: "/settings", icon: Settings },
];

export const OWNER_NAV: NavItem[] = [
  { key: "owner", path: "/owner", icon: ChartLine },
  { key: "reports", path: "/reports", icon: ChartColumn },
  { key: "guests", path: "/guests", icon: Users },
  { key: "backup", path: "/backup", icon: Download },
  { key: "settings", path: "/settings", icon: Settings },
];
