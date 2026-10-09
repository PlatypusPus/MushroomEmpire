import { clock, SEVERITY_COLOR, UNKNOWN_COLOR, type ExposureItem, type Mitigation, type Region, type TimeWindow, type ZonePayload } from "@/api/client"
import { useLiveForecast, useLiveMitigation, useMitigation, useZoneBriefing, useZoneMitigationLive } from "@/api/hooks"
import type { ReactNode } from "react"
import { FlameIcon, HospitalIcon, HouseIcon, PhoneIcon, ShieldIcon } from "lucide-react"
import { cn } from "@/lib/utils"
import { officialStatus } from "@/components/live-hazard"
import { DEFAULT_WEIGHTS, useReplayStore } from "@/state/replayStore"
import { Badge } from "@/components/ui/badge"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ChatPanel } from "@/components/chat-panel"

const TYPE_LABEL: Record<string, string> = {
  hospital: "Hospitals", fire_station: "Fire stations", police: "Police", shelter: "Potential shelters",
  road: "Roads", building: "Buildings",
}
const TYPE_ORDER = ["hospital", "fire_station", "police", "shelter", "road", "building"]
const NAMED = 5

/** One sentence for the zone: the number-checked AI briefing when it adds something, else the alert itself. */
function Summary({ zone, tunable, color }: { zone: ZonePayload; tunable: boolean; color: string }) {
  const { eventId, playing, weights: tuned, mode } = useReplayStore()
  const weights = tunable ? tuned : DEFAULT_WEIGHTS // same weights as the ranking shown beside it
  // the AI briefing reads the replay; a live ranking row is not part of any replay, so it shows its alert text
  const b = useZoneBriefing(zone.zone_id, { event_id: eventId, issue_ts: zone.issue_ts, ...weights }, !playing && mode !== "live")
  const ai = b.data?.source === "llm" ? b.data : null
  return (
    <div className="rounded-md border-l-4 bg-muted/40 p-3" style={{ borderColor: color }}>
      <p className="text-sm leading-relaxed">{ai ? ai.text : zone.alert_text}</p>
      <p className="mt-1.5 text-[11px] text-muted-foreground">
        {playing
          ? "Alert text · AI briefing pauses while the replay plays"
          : ai
            ? `AI briefing · ${ai.model?.replace("ollama/", "")} · every number checked against the data`
            : b.isFetching
              ? "Alert text · writing an AI briefing..."
              : "Alert text"}
      </p>
    </div>
  )
}

function Stat({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="truncate text-base font-semibold capitalize tabular-nums" style={color ? { color } : undefined}>{value}</div>
      {sub && <div className="truncate text-[11px] text-muted-foreground tabular-nums">{sub}</div>}
    </div>
  )
}

function windowSub(w: TimeWindow | null) {
  if (!w) return undefined
  const day = (t: string) => t.slice(0, 10) !== w.likely.slice(0, 10)
  return `${clock(w.earliest, day(w.earliest))} to ${clock(w.latest, day(w.latest))}`
}

/** Global replay stats, rendered as a 4-column strip on top of the Place details card. */
function OverviewStrip({ payloads, region }: { payloads: ZonePayload[]; region: Region | undefined }) {
  const count = (f: (p: ZonePayload) => boolean) => payloads.filter(f).length
  const alerts = count((p) => p.is_alert)
  const unknown = count((p) => p.coverage === "insufficient_data")
  const facilities = payloads
    .filter((p) => p.is_alert)
    .reduce((n, p) => n + p.exposure.filter((a) => a.type === "hospital" || a.type === "shelter").length, 0)
  const items = [
    { label: "Places on alert", value: `${alerts}/${payloads.length}` },
    { label: "Hospitals and shelters", value: String(facilities) },
    { label: "Risk unknown", value: String(unknown) },
  ]
  return (
    <div className="grid grid-cols-3 gap-3 border-b pb-3">
      {items.map((c) => (
        <Stat key={c.label} label={c.label} value={c.value} />
      ))}
    </div>
  )
}

function Facilities({ items }: { items: ExposureItem[] }) {
  if (!items.length) return <p className="text-sm text-muted-foreground">No mapped facilities in this zone.</p>
  const byType = TYPE_ORDER.map((t) => ({ t, list: items.filter((a) => a.type === t) })).filter((g) => g.list.length)
  const hospitals = items.filter((a) => a.type === "hospital")
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-2">
        {byType.map(({ t, list }) => (
          <div key={t} className="rounded-md border px-2.5 py-1.5">
            <div className="text-base font-semibold tabular-nums">{list.length}</div>
            <div className="text-[11px] text-muted-foreground">{TYPE_LABEL[t] ?? t}</div>
          </div>
        ))}
      </div>
      {hospitals.length > 0 && (
        <div>
          <div className="mb-1 text-[11px] text-muted-foreground">Hospitals</div>
          <ul className="text-sm">
            {hospitals.slice(0, NAMED).map((a, i) => <li key={i} className="truncate">{a.name}</li>)}
          </ul>
        </div>
      )}
      <details className="text-sm">
        <summary className="cursor-pointer text-[11px] text-muted-foreground">Show all {items.length}</summary>
        <ul className="mt-1 flex max-h-56 flex-col gap-0.5 overflow-y-auto pr-1">
          {items.map((a, i) => (
            <li key={i} className="flex justify-between gap-2">
              <span className="truncate">{a.name}</span>
              <span className="shrink-0 text-[11px] text-muted-foreground">{a.status === "confirmed" ? "confirmed" : "potential"}</span>
            </li>
          ))}
        </ul>
      </details>
      <p className="text-[11px] text-muted-foreground">Locations from OpenStreetMap. Shelters are schools and community centres, so only potential.</p>
    </div>
  )
}

const NEAR: Record<string, { label: string; icon: ReactNode }> = {
  shelter: { label: "Shelter", icon: <HouseIcon className="size-4 text-sky-500" /> },
  hospital: { label: "Hospital", icon: <HospitalIcon className="size-4 text-red-500" /> },
  fire_station: { label: "Fire", icon: <FlameIcon className="size-4 text-orange-500" /> },
  police: { label: "Police", icon: <ShieldIcon className="size-4 text-blue-500" /> },
}
const directions = (lat: number, lon: number) => `https://www.google.com/maps/dir/?api=1&destination=${lat},${lon}`
const telOf = (phone: string) => `tel:${phone.split(" or ").pop()!.replace(/[^\d]/g, "")}`

function WhatToDo({ zone }: { zone: ZonePayload }) {
  const eventId = useReplayStore((s) => s.eventId)
  const live = useReplayStore((s) => s.mode) === "live"
  const replay = useMitigation(zone.zone_id, { event_id: eventId, issue_ts: zone.issue_ts }, !live)
  const now = useZoneMitigationLive(zone.zone_id, live) // live: follows the official warning level for the place's county
  const m = live ? now : replay
  const color = zone.severity ? SEVERITY_COLOR[zone.severity] : UNKNOWN_COLOR
  return <MitigationView data={m.data} loading={m.isLoading} color={color} />
}

/** Mitigation agent output: one headline, short numbered steps, call buttons, nearest places. Recommends only. */
function MitigationView({ data: d, loading, color }: { data: Mitigation | undefined; loading: boolean; color: string }) {
  if (loading) return <p className="text-sm text-muted-foreground">Loading advice…</p>
  if (!d) return <p className="text-sm text-destructive">Could not load advice for this place.</p>
  const [head, ...rest] = d.steps
  return (
    <div className="flex flex-col gap-4">
      <p className="rounded-lg border-l-4 bg-muted/50 px-3 py-2 text-base font-semibold leading-snug" style={{ borderColor: color }}>
        {head}
        {d.is_simulated && <span className="ml-2 align-middle text-[10px] font-medium uppercase tracking-wide text-muted-foreground">practice</span>}
      </p>
      <ol className="flex flex-col gap-2">
        {rest.map((s, i) => (
          <li key={s} className="flex items-start gap-2.5 text-[15px] font-medium leading-snug">
            <span className="grid size-5 shrink-0 place-items-center rounded-full bg-muted text-[11px] font-bold tabular-nums">{i + 1}</span>
            {s}
          </li>
        ))}
      </ol>
      <div className="flex flex-wrap gap-1.5">
        {d.contacts.map((c) => (
          <a key={c.name} href={telOf(c.phone)} title={c.phone}
            className={cn("inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors hover:bg-muted",
              c.phone === "911" && "border-red-500 bg-red-500 text-white hover:bg-red-600")}>
            <PhoneIcon className="size-3.5" />
            {c.phone === "911" ? "911" : c.name}
          </a>
        ))}
      </div>
      {Object.values(d.nearest).some((l) => l.length > 0) && (
      <ul className="flex flex-col divide-y rounded-lg border">
        {(["shelter", "hospital", "fire_station", "police"] as const).flatMap((k) =>
          d.nearest[k].map((p) => (
            <li key={k + p.name}>
              <a href={directions(p.lat, p.lon)} target="_blank" rel="noreferrer" className="flex items-center gap-2.5 px-3 py-2 text-sm hover:bg-muted/60">
                {NEAR[k].icon}
                <span className="min-w-0 flex-1 truncate">{p.name}</span>
                <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-xs font-semibold tabular-nums">{p.km} km</span>
              </a>
            </li>
          ))
        )}
      </ul>
      )}
      <p className="text-[11px] text-muted-foreground">{d.shelter_note} {d.distance_note}</p>
    </div>
  )
}

/** Our model at the nearest live USGS gauge: a second opinion beside the official warnings, always labelled experimental. */
function LiveForecastBlock({ lat, lon }: { lat: number; lon: number }) {
  const q = useLiveForecast(lat, lon)
  const f = q.data
  const box = "rounded-lg border border-dashed p-3"
  if (q.isLoading) return <div className={`${box} text-sm text-muted-foreground`}>Checking the nearest water gauge…</div>
  if (!f || !f.available) return <div className={`${box} text-xs text-muted-foreground`}>Our forecast: {f?.reason ?? "unavailable right now"}.</div>
  const color = f.severity ? SEVERITY_COLOR[f.severity] : UNKNOWN_COLOR
  const time = (iso: string) => new Date(iso).toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" })
  const learned = f.model.includes("+live")
  return (
    <div className={box}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Our forecast</span>
        <Badge variant="outline" className="border-dashed">Experimental</Badge>
      </div>
      <div className="mt-1 flex items-baseline gap-2">
        <span className="text-3xl font-bold tabular-nums" style={{ color }}>{f.probability == null ? "?" : `${Math.round(f.probability * 100)}%`}</span>
        <span className="text-sm">chance of high water in 24 h</span>
      </div>
      <p className="text-sm font-medium">
        {f.onset
          ? `Likely above its usual high mark from ${time(f.onset)}`
          : f.level_vs_mark_ft >= 0
            ? `Already ${f.level_vs_mark_ft} ft above its usual high mark`
            : `${Math.abs(f.level_vs_mark_ft)} ft below its usual high mark now`}
      </p>
      <a href={f.gauge.url} target="_blank" rel="noreferrer" className="mt-1 block truncate text-[11px] text-muted-foreground underline underline-offset-2">
        {f.gauge.name.toLowerCase()} · {f.gauge.km} km away
      </a>
      <p className="text-[11px] text-muted-foreground">
        {learned ? `Keeps learning from live gauges · updated ${f.trained_at ? new Date(f.trained_at).toLocaleDateString() : ""}` : "Trained on South Florida history"}
        {f.region === "us" ? " · not tested in this area" : ""}
      </p>
    </div>
  )
}

/** Live dashboard: advice where the map was clicked, following the official warnings there (no live forecast exists). */
export function LivePlacePanel({ lat, lon }: { lat: number; lon: number }) {
  const m = useLiveMitigation(lat, lon)
  const d = m.data
  const st = officialStatus(d?.official?.level)
  return (
    <Card data-live-place className="shrink-0 overflow-hidden">
      <div className="h-1.5" style={{ background: d ? st.color : "transparent" }} />
      <CardHeader>
        <CardTitle className="text-2xl font-bold tracking-tight">{d?.name ?? "Checking…"}</CardTitle>
        <CardAction>
          {d && <span className="rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wide" style={{ background: st.color, color: st.ink }}>{st.word}</span>}
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {d?.official && d.official.active.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {d.official.active.map((a) => <Badge key={a} variant="secondary">{a.replace(/ \(.*\)$/, "")}</Badge>)}
          </div>
        )}
        <LiveForecastBlock lat={lat} lon={lon} />
        <MitigationView data={d} loading={m.isLoading} color={st.color} />
        {d?.nearest_failed && <p className="text-xs text-destructive">Nearby places did not load. Retrying soon.</p>}
        <p className="text-[11px] text-muted-foreground">Official warnings, not our forecast · Esc to close</p>
      </CardContent>
    </Card>
  )
}

/** Empty panel: the places most worth a look right now, so nobody is left guessing where to click. */
function TopPlaces({ payloads, names }: { payloads: ZonePayload[]; names: Map<string, string> }) {
  const select = useReplayStore((s) => s.select)
  const top = [...payloads].filter((p) => p.probability != null).sort((a, b) => a.rank - b.rank).slice(0, 3)
  if (!top.length) return null
  return (
    <div className="flex flex-col gap-2">
      <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Highest priority now</div>
      {top.map((p) => (
        <button key={p.zone_id} type="button" onClick={() => select(p.zone_id)}
          className="flex items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors hover:bg-muted">
          <span className="size-3 shrink-0 rounded-full" style={{ background: p.severity ? SEVERITY_COLOR[p.severity] : UNKNOWN_COLOR }} />
          <span className="min-w-0 flex-1 truncate font-semibold">{names.get(p.zone_id) ?? p.zone_id}</span>
          <span className="shrink-0 text-sm font-bold tabular-nums">{Math.round((p.probability ?? 0) * 100)}%</span>
        </button>
      ))}
    </div>
  )
}

export function ZonePanel({ zone, name, tunable = false, payloads, region, names }: { zone: ZonePayload | undefined; name: string | undefined; tunable?: boolean; payloads?: ZonePayload[]; region?: Region; names?: Map<string, string> }) {
  if (!zone) {
    return (
      <Card data-tour="panel" className="flex h-full min-h-0 flex-col overflow-hidden">
        <Tabs defaultValue="details" className="flex min-h-0 flex-1 flex-col">
          <div className="shrink-0 px-(--card-spacing) pt-(--card-spacing)">
            <TabsList variant="line">
              <TabsTrigger value="details">Place Details</TabsTrigger>
              <TabsTrigger value="chat">Chat</TabsTrigger>
            </TabsList>
          </div>
          <TabsContent value="details" className="min-h-0 flex-1 overflow-y-auto p-4">
            <CardHeader>
              <CardDescription>Click a place on the map to see its forecast, why, and nearby facilities.</CardDescription>
            </CardHeader>
            {payloads && (
              <CardContent>
                <div className="flex flex-col gap-4">
                  <OverviewStrip payloads={payloads} region={region} />
                  {names && <TopPlaces payloads={payloads} names={names} />}
                </div>
              </CardContent>
            )}
          </TabsContent>
          <TabsContent value="chat" keepMounted className="flex min-h-0 flex-1 flex-col overflow-hidden px-(--card-spacing) pb-(--card-spacing) [&_[data-slot=card-content]]:px-0">
            <ChatPanel className="flex min-h-0 flex-1 flex-col" />
          </TabsContent>
        </Tabs>
      </Card>
    )
  }
  const unknown = zone.coverage === "insufficient_data"
  const color = zone.severity ? SEVERITY_COLOR[zone.severity] : UNKNOWN_COLOR
  return (
    <Card data-tour="panel" className="flex h-full min-h-0 flex-col overflow-hidden">
      <Tabs defaultValue="details" className="flex min-h-0 flex-1 flex-col">
        <div className="shrink-0 px-(--card-spacing) pt-(--card-spacing)">
          <TabsList variant="line">
            <TabsTrigger value="details">Place Details</TabsTrigger>
            <TabsTrigger value="chat">Chat</TabsTrigger>
          </TabsList>
        </div>
        <TabsContent value="details" className="min-h-0 flex-1 overflow-y-auto">
          <CardHeader>
            <CardTitle className="text-xl">{name ?? zone.zone_id}</CardTitle>
            <CardDescription>Priority #{zone.rank} · {zone.rank_reason}</CardDescription>
            <CardAction className="flex gap-1">
              <Badge variant="outline" className="capitalize">{zone.coverage === "insufficient_data" ? "not enough data" : zone.coverage.replace("_", " ")}</Badge>
              {zone.is_simulated && <Badge variant="destructive">Simulation</Badge>}
            </CardAction>
          </CardHeader>
          <CardContent className="flex flex-col gap-4 pt-6">
            {payloads && <OverviewStrip payloads={payloads} region={region} />}
            {!unknown && (
              <div className="grid grid-cols-4 gap-3">
                <Stat label="Chance" value={`${Math.round((zone.probability ?? 0) * 100)}%`} />
                <Stat label="How bad" value={zone.severity ?? "n/a"} color={color} />
                <Stat label="Starts" value={zone.onset ? clock(zone.onset.likely) : "Not in 24 h"} sub={windowSub(zone.onset)} />
                <Stat label="Worst at" value={zone.peak ? clock(zone.peak.likely) : "Not in 24 h"} sub={windowSub(zone.peak)} />
              </div>
            )}
            <Summary zone={zone} tunable={tunable} color={color} />
            <Tabs defaultValue="why">
              <TabsList>
                <TabsTrigger value="why">Why</TabsTrigger>
                <TabsTrigger value="todo">What to do</TabsTrigger>
                <TabsTrigger value="facilities">Facilities ({zone.exposure.length})</TabsTrigger>
              </TabsList>
              <TabsContent value="why" className="pt-2">
                {zone.reasons?.length ? (
                  <ul className="flex flex-col gap-1.5 text-sm">
                    {zone.reasons.map((r) => (
                      <li key={r.phrase} className="flex items-center justify-between gap-2">
                        <span>{r.phrase}</span>
                        <Badge variant={r.strength === "main reason" ? "default" : "outline"} className="shrink-0">{r.strength}</Badge>
                      </li>
                    ))}
                  </ul>
                ) : zone.drivers_text.length ? (
                  <ul className="list-disc pl-5 text-sm">{zone.drivers_text.map((d) => <li key={d}>{d}</li>)}</ul>
                ) : (
                  <p className="text-sm text-muted-foreground">There is no working water sensor near this place, so we do not know the risk.</p>
                )}
                {zone.model && <p className="mt-2 text-[11px] text-muted-foreground">Model {zone.model}</p>}
              </TabsContent>
              <TabsContent value="todo" className="pt-2">
                <WhatToDo zone={zone} />
              </TabsContent>
              <TabsContent value="facilities" className="pt-2">
                <Facilities items={zone.exposure} />
              </TabsContent>
            </Tabs>
          </CardContent>
        </TabsContent>
        <TabsContent value="chat" keepMounted className="flex min-h-0 flex-1 flex-col overflow-hidden px-(--card-spacing) pb-(--card-spacing) [&_[data-slot=card-content]]:px-0">
          <ChatPanel className="flex min-h-0 flex-1 flex-col" />
        </TabsContent>
      </Tabs>
    </Card>
  )
}
