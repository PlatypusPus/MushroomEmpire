// Live NWS / NHC context. Deliberately a separate, labelled panel: it is NOT part of the historical replay
// and NOT an input to the flood model (ROOT_CONTEXT section 3: live feeds stay visibly separate).
import type { ReactNode } from "react"
import { CloudRainIcon, LeafIcon, WavesIcon, WindIcon } from "lucide-react"

import { SEVERITY_COLOR, UNKNOWN_COLOR } from "@/api/client"
import { useEnvLayers, useLiveContext } from "@/api/hooks"
import { Badge } from "@/components/ui/badge"
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

const WORD = ["No warnings", "Advisory", "Watch", "Warning", "Severe warning"]
const COLOR = [SEVERITY_COLOR.low, SEVERITY_COLOR.moderate, SEVERITY_COLOR.moderate, SEVERITY_COLOR.high, SEVERITY_COLOR.severe]

/** One word and colour per official level (0 none .. 4 most serious; null = feed down, never shown as calm). */
export function officialStatus(level: number | null | undefined) {
  if (level == null) return { word: "Feed down", color: UNKNOWN_COLOR, ink: "#fff" }
  return { word: WORD[level], color: COLOR[level], ink: level <= 2 ? "#111" : "#fff" } // dark text on green/yellow
}

export function LiveDot() {
  return (
    <span className="relative flex size-2.5">
      <span className="absolute inline-flex size-full animate-ping rounded-full bg-red-500 opacity-75" />
      <span className="relative inline-flex size-2.5 rounded-full bg-red-500" />
    </span>
  )
}

function Tile({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-lg bg-muted/50 px-2.5 py-2">
      <div className="flex items-center gap-1 text-[11px] text-muted-foreground">{icon}{label}</div>
      <div className="text-base font-semibold tabular-nums">{value}</div>
    </div>
  )
}

export function LiveHazard() {
  const q = useLiveContext()
  const env = useEnvLayers()
  const c = q.data
  const alerts = c ? Object.entries(c.alerts).flatMap(([county, list]) => list.map((a) => ({ county, ...a }))) : []
  const failed = c ? Object.entries(c.sources).filter(([, s]) => !s.usable).map(([k]) => k) : []
  const st = officialStatus(c?.level)
  const n = (v: number | null | undefined, unit: string) => (v == null ? "n/a" : `${v} ${unit}`)

  return (
    <Card className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="h-1.5 shrink-0" style={{ background: c ? st.color : "transparent" }} />
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg"><LiveDot /> Live now</CardTitle>
        <CardAction><Badge variant="outline">Official</Badge></CardAction>
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto text-sm">
        {q.isLoading && <div className="text-muted-foreground">Checking live feeds…</div>}
        {q.error && <div className="text-muted-foreground">Live feeds offline. The storm replay still works.</div>}
        {c && (
          <>
            <div title={c.heuristic_note}>
              <div className="text-3xl font-bold tracking-tight" style={{ color: st.color }}>{st.word}</div>
              <div className="text-xs text-muted-foreground">South Florida · level {c.level ?? "?"} of 4</div>
            </div>
            {alerts.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {alerts.map((a, i) => (
                  <Badge key={i} variant="secondary" title={a.ends ? `until ${new Date(a.ends).toLocaleString()}` : undefined}>
                    {a.event} · {a.county}
                  </Badge>
                ))}
              </div>
            )}
            {c.cyclones.map((s) => (
              <div key={s.id} className="flex items-center gap-2 rounded-lg border px-3 py-2">
                <WindIcon className="size-4 shrink-0 text-purple-500" />
                <span className="font-semibold">{s.classification === "HU" ? "Hurricane" : s.classification} {s.name}</span>
                <span className="ml-auto text-xs text-muted-foreground">
                  {s.distance_km != null && `${s.distance_km.toLocaleString()} km`}
                  {s.heading_toward_region && " · heading here"}
                </span>
              </div>
            ))}
            <div className="grid grid-cols-2 gap-2">
              {c.forecast && <Tile icon={<CloudRainIcon className="size-3" />} label="Rain 24 h" value={n(c.forecast.rain_next_24h_mm, "mm")} />}
              {c.forecast && <Tile icon={<WindIcon className="size-3" />} label="Gusts 48 h" value={n(c.forecast.max_gust_next_48h_kmh, "km/h")} />}
              {env.data?.marine && <Tile icon={<WavesIcon className="size-3" />} label="Waves" value={n(env.data.marine.wave_height_now_m, "m")} />}
              {env.data?.aqi && <Tile icon={<LeafIcon className="size-3" />} label="Air quality" value={`AQI ${env.data.aqi.us_aqi_now ?? "n/a"}`} />}
            </div>
            <div className="mt-auto text-[11px] text-muted-foreground">
              Weather service and hurricane center, not our forecast · {new Date(c.fetched_at).toLocaleTimeString()}
              {failed.length > 0 && ` · down: ${failed.join(", ")}`}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
