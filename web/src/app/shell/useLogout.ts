import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { api } from "@/api/client";
import { session } from "@/api/session";

export function useLogout() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  return async () => {
    try {
      await api.POST("/api/v1/auth/logout");
    } finally {
      session.signOut();
      queryClient.clear();
      navigate("/login", { replace: true });
    }
  };
}
