import * as React from "react"

import { MapMarker, MapPolygon, MapPolyline, MapPopup } from "@/components/ui/map"

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

/** Live NHC storms: pulsing marker, forecast cone + track, detail popup. Toggle: cyclones. */
export function CycloneLayer() {
  const on = useMapToggles((s) => s.cyclones)
  const { data } = useEnvLayers()
  if (!on || !data) return null

  return (
    <>
      {data.cyclones.map((s) => (
        <React.Fragment key={s.id}>
          {s.cone && s.cone.length > 2 && (
            <MapPolygon
              positions={[s.cone]}
              pathOptions={{ color: "#a855f7", weight: 1.5, opacity: 0.9, dashArray: "5 4", fillColor: "#a855f7", fillOpacity: 0.12, interactive: false }}
            />
          )}
          {s.track && s.track.length > 1 && (
            <MapPolyline positions={s.track} pathOptions={{ color: "#64748b", weight: 2, opacity: 0.85, interactive: false }} />
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
                  NHC advisory {new Date(s.last_update).toLocaleString()} · cone and track are live, not the replay
                </div>
              </div>
            </MapPopup>
          </MapMarker>
        </React.Fragment>
      ))}
    </>
  )
}
