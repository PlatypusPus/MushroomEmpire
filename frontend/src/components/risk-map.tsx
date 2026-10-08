import { Map, MapAutoResize, MapTileLayer, MapZoomControl } from "@/components/ui/map"
import { Card, CardContent } from "@/components/ui/card"

import { type CoastEvent, type Zone, type ZonePayload } from "@/api/client"
import { AlertPolygons } from "./map/AlertPolygons"
import { DashboardMode } from "./dashboard-mode"
import { CycloneLayer, FitLive } from "./map/CycloneLayer"
import { MapLegend } from "./map/MapLegend"
import { MapToggles } from "./map/MapToggles"
import { RadarOverlay } from "./map/RadarOverlay"
import { WindParticles } from "./map/WindParticles"
import { ZoneLayer } from "./map/ZoneLayer"
import { TimeSlider } from "./time-slider"

export function RiskMap({ zones, payloads, events = [], ticks, live = false }: { zones: Zone[]; payloads: ZonePayload[]; events?: CoastEvent[]; ticks?: string[]; live?: boolean }) {
  return (
    <Card className="flex h-full flex-col">
      <CardContent className="flex min-h-0 flex-1 flex-col gap-4">
        <DashboardMode events={events} />
        <div className="min-h-[460px] w-full flex-1 overflow-hidden rounded-lg">
          <Map key={live ? "live" : "replay"} center={[25.95, -80.3]} zoom={8.6} attributionControl>
            <MapAutoResize />
            <MapTileLayer />
            <MapZoomControl />
            <MapToggles />
            {!live && <ZoneLayer zones={zones} payloads={payloads} />}
            <AlertPolygons />
            <CycloneLayer />
            {live && <FitLive />}
            <RadarOverlay />
            <WindParticles />
            <MapLegend live={live} />
          </Map>
        </div>
        {!live && ticks && ticks.length > 0 && <TimeSlider ticks={ticks} bare />}
      </CardContent>
    </Card>
  )
}
