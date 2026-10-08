import { LeafIcon, WavesIcon } from "lucide-react"

import { SEVERITY_COLOR, UNKNOWN_COLOR, type Severity } from "@/api/client"
import { useEnvLayers } from "@/api/hooks"
import { Badge } from "@/components/ui/badge"
import { MapControlContainer } from "@/components/ui/map"
import { useMapToggles } from "@/state/mapLayersStore"

function aqiColor(aqi: number | null): string {
  if (aqi == null) return "text-muted-foreground"
  if (aqi <= 50) return "text-green-500"
  if (aqi <= 100) return "text-yellow-500"
  if (aqi <= 150) return "text-orange-500"
  return "text-red-500"
}

/** Small square legend box, bottom-left: one swatch + label per line. */
export function MapLegend({ live = false }: { live?: boolean }) {
  const marineAqiOn = useMapToggles((s) => s.marineAqi)
  const { data } = useEnvLayers()
  const showEnv = live && marineAqiOn && data && (data.marine || data.aqi)

  return (
    <MapControlContainer className="bottom-1 left-1">
      <div className="flex w-max max-w-44 flex-col gap-1 rounded-md border bg-card/90 px-2 py-1.5 text-[11px] whitespace-nowrap text-muted-foreground shadow-sm backdrop-blur">
        {!live && (Object.keys(SEVERITY_COLOR) as Severity[]).map((s) => (
          <span key={s} className="flex items-center gap-1.5">
            <span className="inline-block size-3 shrink-0 rounded-sm" style={{ backgroundColor: SEVERITY_COLOR[s] }} />
            {s}
          </span>
        ))}
        {!live && (
          <span className="flex items-center gap-1.5">
            <span className="inline-block size-3 shrink-0 rounded-sm" style={{ backgroundColor: UNKNOWN_COLOR }} />
            not enough data
          </span>
        )}
        {/* live items only in Live mode: a replay is a past storm, today's warnings and sea/air would be the wrong time */}
        {live && (<>
        <span className="flex items-center gap-1.5">
          <span className="inline-block size-2.5 shrink-0 rounded-full border-2 border-blue-500" />
          click anywhere: what to do
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4 shrink-0 border-t-2 border-dashed border-orange-500" />
          live weather warning
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block size-2.5 shrink-0 rounded-full bg-orange-500 ring-2 ring-white" />
          live storm
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4 shrink-0 border-t-2 border-dashed border-purple-500" />
          storm path edge
        </span>
        </>)}
        {showEnv && (
          <span className="flex items-center gap-1.5">
            <Badge variant="outline" className="shrink-0 border-dashed px-1 py-0 text-[10px]">
              LIVE
            </Badge>
            {data.marine && (
              <span className="inline-flex items-center gap-1" title="Open-Meteo marine model, not the flood model">
                <WavesIcon className="size-3.5 shrink-0 text-sky-500" />
                {data.marine.wave_height_now_m != null ? `${data.marine.wave_height_now_m} m` : "n/a"}
              </span>
            )}
            {data.aqi && (
              <span className="inline-flex items-center gap-1" title="Open-Meteo air quality, not the flood model">
                <LeafIcon className={`size-3.5 shrink-0 ${aqiColor(data.aqi.us_aqi_now)}`} />
                {data.aqi.us_aqi_now != null ? `AQI ${data.aqi.us_aqi_now}` : "AQI n/a"}
              </span>
            )}
          </span>
        )}
      </div>
    </MapControlContainer>
  )
}
