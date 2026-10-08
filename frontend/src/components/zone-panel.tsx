import { clock, SEVERITY_COLOR, UNKNOWN_COLOR, type TimeWindow, type ZonePayload } from "@/api/client"
import { useZoneBriefing } from "@/api/hooks"
import { DEFAULT_WEIGHTS, useReplayStore } from "@/state/replayStore"
import { Badge } from "@/components/ui/badge"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

const SHOWN_ASSETS = 12

function Briefing({ zone, tunable }: { zone: ZonePayload; tunable: boolean }) {
  const { eventId, playing, weights: tuned } = useReplayStore()
  const weights = tunable ? tuned : DEFAULT_WEIGHTS // same weights as the ranking shown beside it
  const b = useZoneBriefing(zone.zone_id, { event_id: eventId, issue_ts: zone.issue_ts, ...weights }, !playing)
  if (playing) return <div className="text-xs text-muted-foreground">Briefing pauses while the replay plays.</div>
  const duplicate = b.data?.source === "template" && b.data.text === zone.alert_text
  return (
    <div>
      <div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
        Briefing
        {b.data && (
          <Badge variant="outline">{b.data.source === "llm" ? `AI · ${b.data.model?.replace("ollama/", "")} · number-checked` : "template"}</Badge>
        )}
      </div>
      {duplicate ? (
        <p className="text-xs text-muted-foreground">
          Deterministic wording (same as above — the model added nothing{b.data?.reason ? `: ${b.data.reason}` : ""}).
        </p>
      ) : (
        <>
          <p className="text-sm">{b.isFetching && !b.data ? "Writing briefing with the local model..." : b.data?.text}</p>
          {b.data?.source === "template" && b.data?.reason && (
            <p className="mt-1 text-[11px] text-muted-foreground">Fallback: {b.data.reason}</p>
          )}
        </>
      )}
    </div>
  )
}

function Window({ label, w }: { label: string; w: TimeWindow | null }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      {w ? (
        <div className="tabular-nums">
          <span className="text-lg font-semibold">{clock(w.likely)}</span>
          <span className="ml-2 text-xs text-muted-foreground">
            window {clock(w.earliest, w.earliest.slice(0, 10) !== w.likely.slice(0, 10))} to{" "}
            {clock(w.latest, w.latest.slice(0, 10) !== w.likely.slice(0, 10))}
          </span>
        </div>
      ) : (
        <div className="text-sm text-muted-foreground">none expected</div>
      )}
    </div>
  )
}

export function ZonePanel({ zone, name, tunable = false }: { zone: ZonePayload | undefined; name: string | undefined; tunable?: boolean }) {
  if (!zone) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Zone details</CardTitle>
          <CardDescription>Click a zone on the map or in the priority queue.</CardDescription>
        </CardHeader>
      </Card>
    )
  }
  const unknown = zone.coverage === "insufficient_data"
  const color = zone.severity ? SEVERITY_COLOR[zone.severity] : UNKNOWN_COLOR
  return (
    <Card>
      <CardHeader>
        <CardDescription>Rank #{zone.rank} · {zone.rank_reason}</CardDescription>
        <CardTitle className="text-xl">{name ?? zone.zone_id}</CardTitle>
        <CardAction className="flex gap-1">
          <Badge variant="outline">{zone.coverage.replace("_", " ")}</Badge>
          {zone.is_simulated && <Badge variant="destructive">Simulation</Badge>}
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="rounded-md border-l-4 bg-muted/40 p-3 text-sm font-medium" style={{ borderColor: color }}>
          {zone.alert_text}
        </div>
        <Briefing zone={zone} tunable={tunable} />
        {!unknown && (
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-xs text-muted-foreground">Probability</div>
              <div className="text-lg font-semibold tabular-nums">{Math.round((zone.probability ?? 0) * 100)}%</div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Severity</div>
              <div className="text-lg font-semibold capitalize" style={{ color }}>{zone.severity}</div>
            </div>
            <Window label="Onset" w={zone.onset} />
            <Window label="Peak" w={zone.peak} />
          </div>
        )}
        <div>
          <div className="mb-1 text-xs text-muted-foreground">Why</div>
          {zone.explanation && <p className="mb-2 text-sm">{zone.explanation}</p>}
          {zone.reasons?.length ? (
            <ol className="flex flex-col gap-1 text-sm">
              {zone.reasons.map((r) => (
                <li key={r.phrase} className="flex items-center justify-between gap-2">
                  <span>{r.phrase}</span>
                  <Badge variant={r.strength === "main reason" ? "default" : "outline"}>{r.strength}</Badge>
                </li>
              ))}
            </ol>
          ) : zone.drivers_text.length ? (
            <ol className="list-decimal pl-5 text-sm">{zone.drivers_text.map((d) => <li key={d}>{d}</li>)}</ol>
          ) : (
            <div className="text-sm text-muted-foreground">No usable gauge data for this zone.</div>
          )}
          {zone.model && <div className="mt-1 text-xs text-muted-foreground">model: {zone.model}</div>}
        </div>
        <div>
          <div className="mb-1 text-xs text-muted-foreground">
            Facilities in zone ({zone.exposure.length}) · locations from OpenStreetMap
          </div>
          <ul className="flex flex-col gap-1 text-sm">
            {zone.exposure.slice(0, SHOWN_ASSETS).map((a, i) => (
              <li key={i} className="flex items-center justify-between gap-2">
                <span className="truncate">{a.name}</span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {a.type.replace("_", " ")} · {a.status === "confirmed" ? "confirmed" : "potentially exposed"}
                </span>
              </li>
            ))}
          </ul>
          {zone.exposure.length > SHOWN_ASSETS && (
            <div className="mt-1 text-xs text-muted-foreground">+{zone.exposure.length - SHOWN_ASSETS} more</div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
