import { Map, MapAutoResize, MapTileLayer, MapZoomControl } from "@/components/ui/map"
import { Card, CardContent } from "@/components/ui/card"

import { type CoastEvent, type Zone, type ZonePayload } from "@/api/client"
import { AlertPolygons } from "./map/AlertPolygons"
import { DashboardMode } from "./dashboard-mode"
import { CycloneLayer, FitLive } from "./map/CycloneLayer"
import { LivePointPicker } from "./map/LivePointPicker"
import { MapLegend } from "./map/MapLegend"
import { MapToggles } from "./map/MapToggles"
import { RadarOverlay } from "./map/RadarOverlay"
import { WindParticles } from "./map/WindParticles"
import { SpillLayer } from "./map/SpillLayer"
import { ZoneLayer } from "./map/ZoneLayer"
import { TimeSlider } from "./time-slider"

/** `rankedLive`: Response priority in Live mode. Places are coloured by our live (experimental) forecast, official warnings stay,
 * the view stays on South Florida, and replay-only layers (spill zones, time slider) are left out. */
export function RiskMap({ zones, payloads, events = [], ticks, live = false, rankedLive = false }: { zones: Zone[]; payloads: ZonePayload[]; events?: CoastEvent[]; ticks?: string[]; live?: boolean; rankedLive?: boolean }) {
  return (
    <Card className="flex h-full min-h-0 flex-col overflow-hidden">
      <CardContent className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden">
        <DashboardMode events={events} />
        <div data-tour="map" className="min-h-64 w-full flex-1 overflow-hidden rounded-lg">
          <Map key={live ? "live" : "replay"} center={[25.95, -80.3]} zoom={8.6} attributionControl>
            <MapAutoResize />
            <MapTileLayer />
            <MapZoomControl />
            <MapToggles live={live} />
            {/* replay is a past storm: today's warnings, radar, wind and sea state would be the wrong time */}
            {live && rankedLive ? (
              <>
                <ZoneLayer zones={zones} payloads={payloads} />
                <AlertPolygons />
                <CycloneLayer />
              </>
            ) : live ? (
              <>
                <ZoneLayer zones={zones} payloads={[]} live />
                <LivePointPicker />
                <AlertPolygons />
                <CycloneLayer />
                <FitLive />
                <RadarOverlay />
                <WindParticles />
              </>
            ) : (
              <>
                <SpillLayer issueTs={payloads[0]?.issue_ts} />
                <ZoneLayer zones={zones} payloads={payloads} />
              </>
            )}
            <MapLegend live={live && !rankedLive} spill={!live} />
          </Map>
        </div>
        {!live && ticks && ticks.length > 0 && <div data-tour="player"><TimeSlider ticks={ticks} bare /></div>}
      </CardContent>
    </Card>
  )
}
