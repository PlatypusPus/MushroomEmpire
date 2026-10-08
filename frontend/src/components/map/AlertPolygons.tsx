import * as React from "react"
import * as L from "leaflet"
import { useMap } from "react-leaflet"

import { useEnvLayers } from "@/api/hooks"
import { useMapToggles } from "@/state/mapLayersStore"

export const ALERT_LEVEL_COLOR: Record<number, string> = {
  4: "#ef4444",
  3: "#f97316",
  2: "#eab308",
  1: "#38bdf8",
}

/** Live NWS watch/warning polygons. Non-interactive so zone clicks pass through. Toggle: alerts. */
export function AlertPolygons() {
  const map = useMap()
  const on = useMapToggles((s) => s.alerts)
  const { data } = useEnvLayers()
  const layerRef = React.useRef<L.GeoJSON | null>(null)

  React.useEffect(() => {
    const geo = L.geoJSON(undefined, {
      interactive: false,
      style: (f) => {
        const level = (f?.properties as { level?: number } | undefined)?.level ?? 1
        const c = ALERT_LEVEL_COLOR[level] ?? ALERT_LEVEL_COLOR[1]
        return { color: c, weight: 2, opacity: 0.9, dashArray: "7 5", fillColor: c, fillOpacity: 0.07 }
      },
      onEachFeature: (f, layer) => {
        const p = f.properties as { headline?: string; event?: string; counties?: string[] }
        layer.bindTooltip(
          `<b>${p.event ?? "Alert"}</b>${p.counties?.length ? ` · ${p.counties.join(", ")}` : ""}<br/>${p.headline ?? ""}`,
          { sticky: true, direction: "top" }
        )
      },
    })
    layerRef.current = geo
    return () => {
      geo.remove()
      layerRef.current = null
    }
  }, [])

  React.useEffect(() => {
    const geo = layerRef.current
    if (!geo) return
    if (on && data) {
      geo.clearLayers()
      geo.addData(data.alerts_geo as GeoJSON.FeatureCollection)
      if (!map.hasLayer(geo)) geo.addTo(map)
    } else {
      geo.remove()
    }
  }, [on, data, map])

  return null
}
