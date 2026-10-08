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
  config: () => call<{ enabled: boolean; google_client_id: string }>("/auth/config"),
  google: (credential: string) => call<{ token: string; user: Me }>("/auth/google", { method: "POST", body: JSON.stringify({ credential }) }),
  me: () => call<Me>("/me"),
  setZones: (zone_ids: string[]) => call<{ zone_ids: string[] }>("/me/zones", { method: "PUT", body: JSON.stringify({ zone_ids }) }),
  setPrefs: (email_alerts: boolean) => call<{ email_alerts: boolean }>("/me/prefs", { method: "PUT", body: JSON.stringify({ email_alerts }) }),
  alerts: () => call<Delivery[]>("/me/alerts"),
  remove: () => call<void>("/me", { method: "DELETE" }),
}
