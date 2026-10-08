import { LeafIcon, WavesIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { MapControlContainer } from "@/components/ui/map"
import { useEnvLayers } from "@/api/hooks"
import { useMapToggles } from "@/state/mapLayersStore"

function aqiColor(aqi: number | null): string {
  if (aqi == null) return "text-muted-foreground"
  if (aqi <= 50) return "text-green-500"
  if (aqi <= 100) return "text-yellow-500"
  if (aqi <= 150) return "text-orange-500"
  return "text-red-500"
}

/** Live wave + air-quality readout pinned to the map. Toggle: marineAqi. */
export function MarineAqiBadge() {
  const on = useMapToggles((s) => s.marineAqi)
  const { data } = useEnvLayers()
  if (!on || !data || (!data.marine && !data.aqi)) return null

  return (
    <MapControlContainer className="bottom-5 left-1">
      <div className="flex items-center gap-2 rounded-md border border-dashed bg-card/90 px-2 py-1 text-xs shadow-sm backdrop-blur">
        <Badge variant="outline" className="border-dashed px-1 py-0 text-[10px]">
          LIVE
        </Badge>
        {data.marine && (
          <span className="inline-flex items-center gap-1" title="Open-Meteo marine model, not the flood model">
            <WavesIcon className="size-3.5 text-sky-500" />
            {data.marine.wave_height_now_m != null ? `${data.marine.wave_height_now_m} m` : "n/a"}
            {data.marine.wave_height_next_24h_max_m != null && (
              <span className="text-muted-foreground">max {data.marine.wave_height_next_24h_max_m} m / 24 h</span>
            )}
          </span>
        )}
        {data.aqi && (
          <span className="inline-flex items-center gap-1" title="Open-Meteo air quality, not the flood model">
            <LeafIcon className={`size-3.5 ${aqiColor(data.aqi.us_aqi_now)}`} />
            {data.aqi.us_aqi_now != null ? `AQI ${data.aqi.us_aqi_now}` : "AQI n/a"}
          </span>
        )}
      </div>
    </MapControlContainer>
  )
}
