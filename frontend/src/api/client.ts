export type Severity = "low" | "moderate" | "high" | "severe"
export type Coverage =
  | "validated"
  | "experimental"
  | "simulation"
  | "insufficient_data"

export interface Region {
  id: string
  name: string
  kind: "deep" | "transfer"
  coverage: Coverage
  is_simulated: boolean
}

export interface Zone {
  id: string
  region_id: string
  name: string
  county: string | null
  coverage_class: string | null
  geometry: GeoJSON.Polygon
  elevation_m: number | null
  hand_m: number | null
  is_simulated: boolean
}

export interface CoastEvent {
  id: number
  region_id: string
  name: string
  start_ts: string
  end_ts: string
  is_simulated: boolean
  is_holdout: boolean
  source: string
}

export interface TimeWindow {
  earliest: string
  likely: string
  latest: string
}

export interface ExposureItem {
  type: "road" | "building" | "hospital" | "shelter" | "police" | "fire_station"
  name: string
  status: "confirmed" | "potentially_exposed"
}

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
  is_alert: boolean // probability >= the validated alert threshold
  reasons: { theme: string; phrase: string; strength: "main reason" | "important" | "minor" | "standing factor" }[]
  explanation: string | null // one plain sentence built from the reasons
}

export interface AlertEvent {
  issue_ts: string
  zone_id: string
  alert_text: string
  probability: number | null
  severity: Severity | null
  is_simulated: boolean
}

export interface Weights {
  probability: number
  severity: number
  urgency: number
  exposure: number
  vulnerable: number
  uncertainty: number
}

export interface Metrics {
  model: string
  version: string
  region_id: string
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  metrics: Record<string, any> // nested: by_lead, validation, peak_eval, review, ... (see Lane B's model_runs row)
}

export interface LiveAlert {
  event: string
  level: number
  severity: string
  certainty: string
  effective: string
  ends: string | null
  headline: string
}
export interface LiveCyclone {
  id: string
  name: string
  classification: string
  intensity_kt: number | null
  distance_km: number | null
  heading_toward_region: boolean | null
}
export interface LiveContext {
  live: boolean
  note: string
  fetched_at: string
  level: number
  label: string
  heuristic_note: string
  alerts: Record<string, LiveAlert[]>
  cyclones: LiveCyclone[]
  forecast: { source: string; rain_next_24h_mm?: number; rain_next_72h_mm?: number; max_gust_next_48h_kmh?: number } | null
  bulletins: { title: string; published: string; link: string }[]
  sources: Record<string, { ok: boolean; usable: boolean; age_s: number | null; error: string | null }>
  partial: string[]
}

export interface ChatMessage {
  role: "user" | "assistant"
  content: string
}

export interface ChatResponse {
  message: string
  model: string
}

export const SEVERITY_COLOR: Record<Severity, string> = {
  low: "#22c55e",
  moderate: "#eab308",
  high: "#f97316",
  severe: "#ef4444",
}
export const UNKNOWN_COLOR = "#9ca3af" // insufficient data: never green

/** Stored gauge wall clock, never converted: SF2Bench timezone is unknown (ROOT_CONTEXT 20.2f). */
export function clock(ts: string, withDate = false): string {
  const [d, t] = ts.slice(0, 16).split("T")
  const [, m, day] = d.split("-")
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
  return withDate ? `${months[+m - 1]} ${+day}, ${t}` : t
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

function params(query: { [key: string]: unknown }) {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null) q.set(k, String(v))
  }
  const s = q.toString()
  return s ? `?${s}` : ""
}

export interface SnapshotQuery {
  event_id?: number
  issue_ts?: string
}

export const api = {
  health: () => apiFetch<{ ok: boolean }>("/health"),
  regions: (event_id?: number) =>
    apiFetch<Region[]>(`/regions${params({ event_id })}`),
  regionZones: (region_id: string, event_id?: number) =>
    apiFetch<Zone[]>(`/regions/${region_id}/zones${params({ event_id })}`),
  events: () => apiFetch<CoastEvent[]>("/events"),
  zone: (zone_id: string, q: SnapshotQuery = {}) =>
    apiFetch<ZonePayload>(`/zones/${zone_id}${params({ ...q })}`),
  zoneAlert: (zone_id: string, q: SnapshotQuery = {}) =>
    apiFetch<{ zone_id: string; alert_text: string; onset: TimeWindow | null; peak: TimeWindow | null; is_simulated: boolean }>(
      `/zones/${zone_id}/alert${params({ ...q })}`
    ),
  zoneExplanation: (zone_id: string, q: SnapshotQuery = {}) =>
    apiFetch<{ zone_id: string; drivers_text: string[]; model: string | null }>(
      `/zones/${zone_id}/explanation${params({ ...q })}`
    ),
  zoneExposure: (zone_id: string, event_id?: number) =>
    apiFetch<ExposureItem[]>(`/zones/${zone_id}/exposure${params({ event_id })}`),
  ranking: (q: SnapshotQuery & Partial<Weights> = {}) =>
    apiFetch<ZonePayload[]>(`/ranking${params({ ...q })}`),
  rankingWeights: (weights: Partial<Weights>, q: SnapshotQuery = {}) =>
    apiFetch<ZonePayload[]>("/ranking/weights", {
      method: "POST",
      body: JSON.stringify({ weights, ...q }),
    }),
  zoneBriefing: (zone_id: string, q: SnapshotQuery & Partial<Weights> = {}) =>
    apiFetch<{ zone_id: string; text: string; source: "llm" | "template"; model: string | null; reason: string | null }>(
      `/zones/${zone_id}/briefing${params({ ...q })}`
    ),
  replayAlerts: (session_id: string, upto: number) =>
    apiFetch<AlertEvent[]>(`/replay/${session_id}/alerts${params({ upto })}`),
  replayStart: (event_id: number, step_h: number) =>
    apiFetch<{ session_id: string; event_id: number; ticks: string[] }>(
      `/replay/${event_id}/start${params({ step_h })}`,
      { method: "POST" }
    ),
  context: () => apiFetch<LiveContext>("/context"),
  metrics: (region_id: string, event_id?: number) =>
    apiFetch<Metrics[]>(`/models/${region_id}/metrics${params({ event_id })}`),
  chat: (messages: ChatMessage[], system?: string) =>
    apiFetch<ChatResponse>("/chat", {
      method: "POST",
      body: JSON.stringify({ messages, system }),
    }),
}

/** Token stream for POST /api/chat/stream (SSE). Calls onToken per token,
 * resolves with the model name on done, throws ApiError on error events
 * or HTTP failures. Thinking spans never arrive: stripped server-side. */
export async function streamChat(
  messages: ChatMessage[],
  onToken: (token: string) => void,
  opts: { system?: string; signal?: AbortSignal } = {}
): Promise<string> {
  const res = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, system: opts.system }),
    signal: opts.signal,
  })
  if (!res.ok || !res.body) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ""
  let model = ""
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const parts = buf.split("\n\n")
    buf = parts.pop() ?? ""
    for (const part of parts) {
      for (const line of part.split("\n")) {
        if (!line.startsWith("data:")) continue
        const evt = JSON.parse(line.slice(5).trim()) as {
          token?: string
          error?: string
          done?: boolean
          model?: string
        }
        if (typeof evt.token === "string") onToken(evt.token)
        else if (typeof evt.error === "string") throw new ApiError(503, evt.error)
        else if (evt.done) model = evt.model ?? ""
      }
    }
  }
  return model
}

export interface AssistantResult {
  model: string | null
  intent: string | null
  zone_id: string | null
  source: string | null
}

/** Token stream for POST /api/assistant/stream (SSE, grounded).
 * Sends one question naming the place each time (e.g.
 * "What is the status at Fort Lauderdale?") plus the dashboard's current
 * event/issue_ts/weights so the answer reuses the already-computed tick
 * cache and matches the ranking on screen. The server routes to the
 * agents' ZonePayload outputs, number-checks the answer and streams the
 * guarded text in word chunks. Resolves with intent/zone/source metadata. */
export async function streamAssistant(
  question: string,
  onToken: (token: string) => void,
  opts: { event_id?: number; issue_ts?: string; weights?: Weights; signal?: AbortSignal; onStatus?: (status: string) => void } = {}
): Promise<AssistantResult> {
  const res = await fetch("/api/assistant/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, event_id: opts.event_id, issue_ts: opts.issue_ts, weights: opts.weights }),
    signal: opts.signal,
  })
  if (!res.ok || !res.body) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ""
  const out: AssistantResult = { model: null, intent: null, zone_id: null, source: null }
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const parts = buf.split("\n\n")
    buf = parts.pop() ?? ""
    for (const part of parts) {
      for (const line of part.split("\n")) {
        if (!line.startsWith("data:")) continue
        const evt = JSON.parse(line.slice(5).trim()) as {
          token?: string
          status?: string
          error?: string
          done?: boolean
          model?: string | null
          intent?: string | null
          zone_id?: string | null
          source?: string | null
        }
        if (typeof evt.token === "string") onToken(evt.token)
        else if (typeof evt.status === "string") opts.onStatus?.(evt.status)
        else if (typeof evt.error === "string") throw new ApiError(503, evt.error)
        else if (evt.done) {
          out.model = evt.model ?? null
          out.intent = evt.intent ?? null
          out.zone_id = evt.zone_id ?? null
          out.source = evt.source ?? null
        }
      }
    }
  }
  return out
}
