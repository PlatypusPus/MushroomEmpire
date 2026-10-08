import * as React from "react"
import { useMap } from "react-leaflet"

import { MapMarker, MapPolygon, MapPopup } from "@/components/ui/map"

import { useEnvLayers } from "@/api/hooks"
import type { EnvCyclone } from "@/api/client"
import { useMapToggles } from "@/state/mapLayersStore"

/** Region centre, matching backend REGION (South Florida). */
export const REGION_CENTER: [number, number] = [25.8, -80.2]

function classLabel(c: EnvCyclone): string {
  const base =
    c.classification === "HU" ? "Hurricane" : c.classification === "TS" ? "Tropical Storm" : c.classification === "TD" ? "Tropical Depression" : c.classification
  return `${base} ${c.name}`
}

/** Live NHC storms: pulsing marker, forecast cone boundary, detail popup. Toggle: cyclones. */
export function CycloneLayer() {
  const on = useMapToggles((s) => s.cyclones)
  const { data } = useEnvLayers()
  if (!on || !data) return null

  return (
    <>
      {data.cyclones.map((s) => (
        <React.Fragment key={s.id}>
          {/* boundary only: the forecast cone outline, no fill and no centre-track line */}
          {s.cone && s.cone.length > 2 && (
            <MapPolygon
              positions={[s.cone]}
              // MapPolygon's default class paints fill and stroke with the foreground colour (a solid white cone); CSS beats the SVG attributes, so override it
              className="fill-transparent stroke-purple-500 stroke-2"
              pathOptions={{ color: "#a855f7", weight: 2, opacity: 0.95, dashArray: "6 4", fill: false, interactive: false }}
            />
          )}
          <MapMarker
            position={[s.lat, s.lon]}
            iconAnchor={[12, 12]}
            icon={
              <span className="relative flex size-6 items-center justify-center">
                <span className="cyclone-ping absolute inline-flex size-full rounded-full bg-orange-500" />
                <span className="relative inline-flex size-3 rounded-full bg-orange-500 ring-2 ring-white" />
              </span>
            }
          >
            <MapPopup>
              <div className="text-sm">
                <div className="font-semibold">{classLabel(s)}</div>
                <div className="text-muted-foreground">
                  {s.intensity_kt != null && `${s.intensity_kt} kt · `}
                  {s.distance_km != null && `${s.distance_km.toLocaleString()} km from the region`}
                  {s.heading_toward_region && " · heading this way"}
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  NHC advisory {new Date(s.last_update).toLocaleString()} · cone is live, not the replay
                </div>
              </div>
            </MapPopup>
          </MapMarker>
        </React.Fragment>
      ))}
    </>
  )
}

/** Live view: zoom out once so the storm's forecast cone and the region are both in frame (a distant storm is otherwise off-screen). */
export function FitLive() {
  const map = useMap()
  const { data } = useEnvLayers()
  const key = data?.cyclones.map((c) => c.id).join(",") ?? ""
  React.useEffect(() => {
    const pts = (data?.cyclones ?? []).flatMap((c) => (c.cone?.length ? c.cone.filter((_, i) => i % 10 === 0) : [[c.lat, c.lon] as [number, number]]))
    if (pts.length) map.fitBounds([REGION_CENTER, ...pts], { padding: [30, 30], maxZoom: 8 })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, map])
  return null
}
