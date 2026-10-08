// Live NWS / NHC context. Deliberately a separate, labelled panel: it is NOT part of the historical replay
// and NOT an input to the flood model (ROOT_CONTEXT section 3: live feeds stay visibly separate).
import { RadioIcon } from "lucide-react"

import { useEnvLayers, useLiveContext } from "@/api/hooks"
import { Badge } from "@/components/ui/badge"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export function LiveHazard() {
  const q = useLiveContext()
  const env = useEnvLayers()
  const c = q.data
  const alerts = c ? Object.entries(c.alerts).flatMap(([county, list]) => list.map((a) => ({ county, ...a }))) : []
  const failed = c ? Object.entries(c.sources).filter(([, s]) => !s.usable).map(([k]) => k) : []

  return (
    <Card className="h-full border-dashed">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <RadioIcon className="size-4" /> Live hazard context
        </CardTitle>
        <CardDescription>
          Live today from the weather service and the hurricane center. It is separate from the storm replay and is not used by our flood forecast.
        </CardDescription>
        <CardAction>
          <Badge variant="outline">LIVE</Badge>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        {q.isLoading && <div className="text-muted-foreground">Checking live feeds...</div>}
        {q.error && <div className="text-muted-foreground">Live feeds unavailable (offline?). The storm replay is unaffected.</div>}
        {c && (
          <>
            <div>
              <span className="font-medium capitalize">{c.label}</span>
              <span className="ml-2 text-xs text-muted-foreground">level {c.level} of 4 · {c.heuristic_note}</span>
            </div>
            {alerts.length > 0 ? (
              <ul className="flex flex-col gap-1">
                {alerts.map((a, i) => (
                  <li key={i}>
                    <span className="font-medium">{a.event}</span>
                    <span className="text-muted-foreground"> · {a.county} · {a.severity}, {a.certainty.toLowerCase()}</span>
                    {a.ends && <span className="text-muted-foreground"> · until {new Date(a.ends).toLocaleString()}</span>}
                  </li>
                ))}
              </ul>
            ) : (
              <div className="text-muted-foreground">No weather warnings right now for Miami-Dade or Broward.</div>
            )}
            {c.cyclones.map((s) => (
              <div key={s.id}>
                <span className="font-medium">{s.classification === "HU" ? "Hurricane" : s.classification} {s.name}</span>
                <span className="text-muted-foreground">
                  {s.distance_km != null && ` · ${s.distance_km.toLocaleString()} km away`}
                  {s.heading_toward_region && " · heading toward South Florida"}
                </span>
              </div>
            ))}
            {c.forecast && (
              <div className="text-xs text-muted-foreground">
                Weather forecast (not ours): rain in the next 24 h {c.forecast.rain_next_24h_mm ?? "n/a"} mm, strongest gust in the next 48 h{" "}
                {c.forecast.max_gust_next_48h_kmh ?? "n/a"} km/h.
              </div>
            )}
            {env.data && (env.data.marine || env.data.aqi) && (
              <div className="text-xs text-muted-foreground">
                Sea and air (not our forecast):
                {env.data.marine && (
                  <> waves now {env.data.marine.wave_height_now_m ?? "n/a"} m, up to {env.data.marine.wave_height_next_24h_max_m ?? "n/a"} m in 24 h</>
                )}
                {env.data.marine && env.data.aqi && " · "}
                {env.data.aqi && (
                  <> AQI {env.data.aqi.us_aqi_now ?? "n/a"} (PM2.5 {env.data.aqi.pm2_5_now ?? "n/a"} µg/m³)</>
                )}
                .
              </div>
            )}
            <div className="text-xs text-muted-foreground">
              Fetched {new Date(c.fetched_at).toLocaleTimeString()}
              {failed.length > 0 && ` · not working: ${failed.join(", ")}`}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
