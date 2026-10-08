import { useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

// Accounts client. The session token (our own short-lived JWT, never the Google one) lives in localStorage.
const KEY = "kadal.token"

export interface Me { id: number; email: string; name: string; email_alerts: boolean; zone_ids: string[] }
export interface Delivery { id: number; kind: "replay" | "live"; zone_id: string | null; title: string; body: string; created_at: string; status: string }

export const token = {
  get: () => { try { return localStorage.getItem(KEY) } catch { return null } },
  set: (t: string) => { try { localStorage.setItem(KEY, t) } catch { /* private mode: session lasts until reload */ } },
  clear: () => { try { localStorage.removeItem(KEY) } catch { /* nothing stored */ } },
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const t = token.get()
  const r = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}), ...init.headers },
  })
  if (r.status === 401) token.clear()
  if (!r.ok) throw new Error(`${r.status}`)
  return r.status === 204 ? (undefined as T) : r.json()
}

export const account = {
  config: () => call<{ enabled: boolean; providers: { id: string; label: string; login_url: string }[] }>("/auth/config"),
  me: () => call<Me>("/me"),
  setZones: (zone_ids: string[]) => call<{ zone_ids: string[] }>("/me/zones", { method: "PUT", body: JSON.stringify({ zone_ids }) }),
  setPrefs: (email_alerts: boolean) => call<{ email_alerts: boolean }>("/me/prefs", { method: "PUT", body: JSON.stringify({ email_alerts }) }),
  alerts: () => call<Delivery[]>("/me/alerts"),
  remove: () => call<void>("/me", { method: "DELETE" }),
  testEmail: () => call<{ status: "sent" | "outbox" | "failed"; to: string }>("/me/test-email", { method: "POST" }),
}

/** The signed-in user, or null when signed out. One shared query so the sidebar and the account page never disagree. */
export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: async (): Promise<Me | null> => {
      if (!token.get()) return null
      try { return await account.me() } catch { return null } // expired or revoked token: treat as signed out (call() already cleared it)
    },
    staleTime: 60_000,
    retry: false,
  })
}

export function useSignOut() {
  const qc = useQueryClient()
  return () => {
    token.clear()
    qc.setQueryData(["me"], null) // set, not clear(): clear() detaches live observers, so the page would keep showing the old user
    qc.removeQueries({ queryKey: ["my-alerts"] })
    toast("Signed out")
  }
}
