import { clock, SEVERITY_COLOR, UNKNOWN_COLOR, type ExposureItem, type TimeWindow, type ZonePayload } from "@/api/client"
import { useZoneBriefing } from "@/api/hooks"
import { DEFAULT_WEIGHTS, useReplayStore } from "@/state/replayStore"
import { Badge } from "@/components/ui/badge"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

const TYPE_LABEL: Record<string, string> = {
  hospital: "Hospitals", fire_station: "Fire stations", police: "Police", shelter: "Potential shelters",
  road: "Roads", building: "Buildings",
}
const TYPE_ORDER = ["hospital", "fire_station", "police", "shelter", "road", "building"]
const NAMED = 5

/** One sentence for the zone: the number-checked AI briefing when it adds something, else the alert itself. */
function Summary({ zone, tunable, color }: { zone: ZonePayload; tunable: boolean; color: string }) {
  const { eventId, playing, weights: tuned } = useReplayStore()
  const weights = tunable ? tuned : DEFAULT_WEIGHTS // same weights as the ranking shown beside it
  const b = useZoneBriefing(zone.zone_id, { event_id: eventId, issue_ts: zone.issue_ts, ...weights }, !playing)
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

export function ZonePanel({ zone, name, tunable = false }: { zone: ZonePayload | undefined; name: string | undefined; tunable?: boolean }) {
  if (!zone) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Place details</CardTitle>
          <CardDescription>Click a place on the map to see its forecast, why, and nearby facilities.</CardDescription>
        </CardHeader>
      </Card>
    )
  }
  const unknown = zone.coverage === "insufficient_data"
  const color = zone.severity ? SEVERITY_COLOR[zone.severity] : UNKNOWN_COLOR
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl">{name ?? zone.zone_id}</CardTitle>
        <CardDescription>Priority #{zone.rank} · {zone.rank_reason}</CardDescription>
        <CardAction className="flex gap-1">
          <Badge variant="outline" className="capitalize">{zone.coverage === "insufficient_data" ? "not enough data" : zone.coverage.replace("_", " ")}</Badge>
          {zone.is_simulated && <Badge variant="destructive">Simulation</Badge>}
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {!unknown && (
          <div className="grid grid-cols-4 gap-3">
            <Stat label="Chance" value={`${Math.round((zone.probability ?? 0) * 100)}%`} />
            <Stat label="How bad" value={zone.severity ?? "n/a"} color={color} />
            <Stat label="Starts" value={zone.onset ? clock(zone.onset.likely) : "none"} sub={windowSub(zone.onset)} />
            <Stat label="Worst at" value={zone.peak ? clock(zone.peak.likely) : "none"} sub={windowSub(zone.peak)} />
          </div>
        )}
        <Summary zone={zone} tunable={tunable} color={color} />
        <Tabs defaultValue="why">
          <TabsList>
            <TabsTrigger value="why">Why</TabsTrigger>
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
          <TabsContent value="facilities" className="pt-2">
            <Facilities items={zone.exposure} />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  )
}
