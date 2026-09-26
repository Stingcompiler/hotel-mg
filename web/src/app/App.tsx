import { DirectionProvider } from "@radix-ui/react-direction";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useSyncExternalStore } from "react";
import { createBrowserRouter, Navigate, RouterProvider, useLocation } from "react-router-dom";

import { useHotelSettings, useSystemStatus } from "@/api/queries";
import { session } from "@/api/session";
import { CashPage } from "@/features/cash/CashPage";
import { ExpensesPage } from "@/features/expenses/ExpensesPage";
import { FollowupsPage } from "@/features/followups/FollowupsPage";
import { GuestsPage } from "@/features/guests/GuestsPage";
import { LoginPage } from "@/features/login/LoginPage";
import { Placeholder } from "@/features/placeholder/Placeholder";
import { ReportsPage } from "@/features/reports/ReportsPage";
import { NewReservationPage } from "@/features/reservations/NewReservationPage";
import { ReservationsPage } from "@/features/reservations/ReservationsPage";
import { RoomBoardPage } from "@/features/rooms/RoomBoardPage";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { StayDetailPage } from "@/features/stays/StayDetailPage";
import { setDigits } from "@/i18n/digits";
import { setMoneyDecimals } from "@/i18n/money";
import { t } from "@/i18n/t";

import { OwnerShell } from "./shell/OwnerShell";
import { ReceptionShell } from "./shell/ReceptionShell";

export const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 10_000, refetchOnWindowFocus: true, retry: 1 } },
});

function useSignedIn() {
  return useSyncExternalStore(session.subscribe.bind(session), () => !!session.token);
}

/** Picks the shell from `system/status.role` (spec §10.4) and applies the hotel's digit/money settings. */
function Root() {
  const signedIn = useSignedIn();
  const status = useSystemStatus();
  const settings = useHotelSettings().data;
  const location = useLocation();

  useEffect(() => {
    if (settings) {
      setDigits(settings.digits);
      setMoneyDecimals(settings.money_decimals);
    }
  }, [settings]);

  if (!signedIn) return <Navigate to="/login" replace />;
  if (!status.data) return <div className="p-6 text-text-secondary">{t("common.loading")}</div>;
  session.role = status.data.role;
  if (status.data.role === "owner") {
    return location.pathname === "/" ? <Navigate to="/owner" replace /> : <OwnerShell />;
  }
  return <ReceptionShell />;
}

const screen = (path: string, key: string) => ({ path, element: <Placeholder titleKey={`nav.${key}`} /> });

const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    element: <Root />,
    children: [
      { path: "/", element: <RoomBoardPage /> },
      { path: "/reservations", element: <ReservationsPage /> },
      { path: "/reservations/new", element: <NewReservationPage /> },
      { path: "/stays/:id", element: <StayDetailPage /> },
      { path: "/followups", element: <FollowupsPage /> },
      { path: "/cash", element: <CashPage /> },
      { path: "/expenses", element: <ExpensesPage /> },
      { path: "/guests", element: <GuestsPage /> },
      { path: "/reports", element: <ReportsPage /> },
      { path: "/reports/:name", element: <ReportsPage /> },
      { path: "/settings", element: <SettingsPage /> },
      { path: "/settings/:tab", element: <SettingsPage /> },
      screen("/owner", "owner"),
      screen("/backup", "backup"),
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
], { future: { v7_relativeSplatPath: true } });

export function App() {
  return (
    <DirectionProvider dir="rtl">
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} future={{ v7_startTransition: true }} />
      </QueryClientProvider>
    </DirectionProvider>
  );
}

