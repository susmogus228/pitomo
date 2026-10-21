import type { User } from "./types";

export function adminAccess(user: User | null, authLoading: boolean, sessionError: string): "loading" | "error" | "login" | "denied" | "allowed" {
  if (authLoading) return "loading";
  if (sessionError) return "error";
  if (!user) return "login";
  return user.role === "admin" && user.is_active ? "allowed" : "denied";
}
