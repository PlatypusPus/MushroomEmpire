import { Map, MapTileLayer, MapZoomControl } from "@/components/ui/map"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

import { SEVERITY_COLOR, UNKNOWN_COLOR, type Severity, type Zone, type ZonePayload } from "@/api/client"
import { AlertPolygons } from "./map/AlertPolygons"
import { CycloneLayer } from "./map/CycloneLayer"
import { MapToggles } from "./map/MapToggles"
import { MarineAqiBadge } from "./map/MarineAqiBadge"
import { RadarOverlay } from "./map/RadarOverlay"
import { WindParticles } from "./map/WindParticles"
import { ZoneLayer } from "./map/ZoneLayer"

export function RiskMap({ zones, payloads }: { zones: Zone[]; payloads: ZonePayload[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>High-water risk map</CardTitle>
        <CardDescription>
          Census places coloured by severity at the current replay time. Click a zone for details. Layers and animations toggle top-right.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-[460px] w-full overflow-hidden rounded-lg border">
          <Map center={[25.95, -80.3]} zoom={8.6} attributionControl>
            <MapTileLayer />
            <MapZoomControl />
            <MapToggles />
            <ZoneLayer zones={zones} payloads={payloads} />
            <AlertPolygons />
            <CycloneLayer />
            <RadarOverlay />
            <WindParticles />
            <MarineAqiBadge />
          </Map>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted-foreground">
          {(Object.keys(SEVERITY_COLOR) as Severity[]).map((s) => (
            <span key={s} className="inline-flex items-center gap-1.5">
              <span className="inline-block size-3 rounded-sm" style={{ backgroundColor: SEVERITY_COLOR[s] }} />
              {s}
            </span>
          ))}
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block size-3 rounded-sm" style={{ backgroundColor: UNKNOWN_COLOR }} />
            insufficient data (unknown, not safe)
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-4 border-t-2 border-dashed border-orange-500" />
            live NWS alert
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block size-2.5 rounded-full bg-orange-500 ring-2 ring-white" />
            live cyclone
          </span>
        </div>
      </CardContent>
    </Card>
  )
}
