import { Map, MapTileLayer, MapZoomControl } from "@/components/ui/map"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

import { SEVERITY_COLOR, UNKNOWN_COLOR, type Severity, type Zone, type ZonePayload } from "@/api/client"
import { AlertPolygons } from "./map/AlertPolygons"
import { CycloneLayer, FitLive } from "./map/CycloneLayer"
import { LivePointPicker } from "./map/LivePointPicker"
import { MapToggles } from "./map/MapToggles"
import { MarineAqiBadge } from "./map/MarineAqiBadge"
import { RadarOverlay } from "./map/RadarOverlay"
import { WindParticles } from "./map/WindParticles"
import { ZoneLayer } from "./map/ZoneLayer"

export function RiskMap({ zones, payloads, live = false }: { zones: Zone[]; payloads: ZonePayload[]; live?: boolean }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{live ? "Live warnings map" : "Flood risk map"}</CardTitle>
        <CardDescription>
          {live
            ? "Live warnings for South Florida from the weather service and the hurricane center: warning areas and the storm's possible path. This is not our flood forecast. Click anywhere, inside or outside South Florida, for what to do there and where the nearest shelters are."
            : "Towns and cities coloured by how bad the flood risk is at the time shown. Click one for details. Map layers are in the top-right menu."}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-[460px] w-full overflow-hidden rounded-lg border">
          <Map key={live ? "live" : "replay"} center={[25.95, -80.3]} zoom={8.6} attributionControl>
            <MapTileLayer />
            <MapZoomControl />
            <MapToggles live={live} />
            {/* replay is a past storm: today's warnings, radar, wind and sea state would be the wrong time */}
            {live ? (
              <>
                <ZoneLayer zones={zones} payloads={[]} live />
                <LivePointPicker />
                <AlertPolygons />
                <CycloneLayer />
                <FitLive />
                <RadarOverlay />
                <WindParticles />
                <MarineAqiBadge />
              </>
            ) : (
              <ZoneLayer zones={zones} payloads={payloads} />
            )}
          </Map>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted-foreground">
          {!live && (Object.keys(SEVERITY_COLOR) as Severity[]).map((s) => (
            <span key={s} className="inline-flex items-center gap-1.5">
              <span className="inline-block size-3 rounded-sm" style={{ backgroundColor: SEVERITY_COLOR[s] }} />
              {s}
            </span>
          ))}
          {!live && (
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-block size-3 rounded-sm" style={{ backgroundColor: UNKNOWN_COLOR }} />
              not enough data (risk unknown, not safe)
            </span>
          )}
          {live && (<>
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-4 border-t-2 border-dashed border-orange-500" />
            live weather warning
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block size-2.5 rounded-full bg-orange-500 ring-2 ring-white" />
            live storm
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-4 border-t-2 border-dashed border-purple-500" />
            edge of the storm's possible path
          </span>
          </>)}
        </div>
      </CardContent>
    </Card>
  )
}
