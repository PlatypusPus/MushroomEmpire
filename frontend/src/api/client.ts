// Typed wrappers for the backend contract (backend/app/schemas.py, ROOT_CONTEXT section 9).
import { keepPreviousData, useQuery } from "@tanstack/react-query"

export type Severity = "low" | "moderate" | "high" | "severe"
export type Coverage = "validated" | "experimental" | "simulation" | "insufficient_data"

export interface TimeWindow { earliest: string; likely: string; latest: string }
export interface ExposureItem { type: string; name: string; status: "confirmed" | "potentially_exposed" }
export interface ZonePayload {
  zone_id: string
  issue_ts: string
  coverage: Coverage
  is_simulated: boolean
  probability: number | null
  severity: Severity | null
  onset: TimeWindow | null
  peak: TimeWindow | null
  drivers_text: string[]
  exposure: ExposureItem[]
  rank: number
  rank_reason: string
  alert_text: string
  model: string | null
}
export interface Zone { id: string; region_id: string; name: string; county: string | null; geometry: GeoJSON.Polygon }
export interface Region { id: string; name: string; coverage: Coverage }
export interface Event { id: number; name: string; start_ts: string; end_ts: string; is_holdout: boolean }
export interface Weights {
  probability: number; severity: number; urgency: number; exposure: number; vulnerable: number; uncertainty: number
}

/** Stored gauge wall clock, never converted: SF2Bench timezone is unknown (ROOT_CONTEXT 20.2f). */
export function clock(ts: string, withDate = false): string {
  const [d, t] = ts.slice(0, 16).split("T")
  const [, m, day] = d.split("-")
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
  return withDate ? `${months[+m - 1]} ${+day}, ${t}` : t
}

export const SEVERITY_COLOR: Record<Severity, string> = {
  low: "#22c55e", moderate: "#eab308", high: "#f97316", severe: "#ef4444",
}
export const UNKNOWN_COLOR = "#9ca3af"

async function get<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, init)
  if (!r.ok) throw new Error(`${r.status} ${path}`)
  return r.json()
}

export const useEvents = () => useQuery({ queryKey: ["events"], queryFn: () => get<Event[]>("/api/events") })

export const useRegion = (eventId: number) =>
  useQuery({ queryKey: ["regions", eventId], queryFn: () => get<Region[]>(`/api/regions?event_id=${eventId}`).then((r) => r[0]) })

export const useZones = (regionId: string | undefined, eventId: number) =>
  useQuery({
    queryKey: ["zones", regionId, eventId],
    enabled: !!regionId,
    queryFn: () => get<Zone[]>(`/api/regions/${regionId}/zones?event_id=${eventId}`),
  })

export const useReplay = (eventId: number, stepH: number) =>
  useQuery({
    queryKey: ["replay", eventId, stepH],
    staleTime: Infinity,
    queryFn: () => get<{ session_id: string; ticks: string[] }>(`/api/replay/${eventId}/start?step_h=${stepH}`, { method: "POST" }),
  })

/** One call per tick: every zone's payload, already ranked under the given weights. */
export const useTick = (eventId: number, issueTs: string | undefined, w: Weights) =>
  useQuery({
    queryKey: ["tick", eventId, issueTs, w],
    enabled: !!issueTs,
    placeholderData: keepPreviousData,
    queryFn: () => {
      const q = new URLSearchParams({ event_id: String(eventId), issue_ts: issueTs! })
      Object.entries(w).forEach(([k, v]) => q.set(k, String(v)))
      return get<ZonePayload[]>(`/api/ranking?${q}`)
    },
  })
