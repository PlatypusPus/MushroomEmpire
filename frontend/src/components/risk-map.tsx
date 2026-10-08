import * as React from "react"
import maplibregl, { type Map as MLMap, type MapLayerMouseEvent } from "maplibre-gl"
import "maplibre-gl/dist/maplibre-gl.css"
import { useTheme } from "next-themes"

import { SEVERITY_COLOR, UNKNOWN_COLOR, type Severity, type Zone, type ZonePayload } from "@/api/client"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { useReplayStore } from "@/state/replayStore"

const LIGHT_STYLE = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
const DARK_STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
const SOURCE_ID = "coastguard-zones"

const fill: maplibregl.ExpressionSpecification = [
  "match", ["get", "severity"],
  "severe", SEVERITY_COLOR.severe, "high", SEVERITY_COLOR.high,
  "moderate", SEVERITY_COLOR.moderate, "low", SEVERITY_COLOR.low,
  UNKNOWN_COLOR, // insufficient data: grey, never green
]

function toGeoJSON(zones: Zone[], payloads: ZonePayload[]): GeoJSON.FeatureCollection {
  const by = new Map(payloads.map((p) => [p.zone_id, p]))
  return {
    type: "FeatureCollection",
    features: zones.map((z) => {
      const p = by.get(z.id)
      return {
        type: "Feature",
        geometry: z.geometry,
        properties: { zone_id: z.id, name: z.name, severity: p?.severity ?? "unknown" },
      }
    }),
  }
}

export function RiskMap({ zones, payloads }: { zones: Zone[]; payloads: ZonePayload[] }) {
  const containerRef = React.useRef<HTMLDivElement | null>(null)
  const mapRef = React.useRef<MLMap | null>(null)
  const dataRef = React.useRef<GeoJSON.FeatureCollection>(toGeoJSON(zones, payloads))
  const { resolvedTheme } = useTheme()
  const selected = useReplayStore((s) => s.selectedZone)
  const select = useReplayStore((s) => s.select)

  const addLayers = React.useCallback(() => {
    const map = mapRef.current
    if (!map || map.getSource(SOURCE_ID)) return
    map.addSource(SOURCE_ID, { type: "geojson", data: dataRef.current })
    map.addLayer({ id: "zones-fill", type: "fill", source: SOURCE_ID, paint: { "fill-color": fill, "fill-opacity": 0.5 } })
    map.addLayer({ id: "zones-outline", type: "line", source: SOURCE_ID, paint: { "line-color": fill, "line-width": 1 } })
    map.addLayer({
      id: "zones-selected", type: "line", source: SOURCE_ID,
      paint: { "line-color": "#3b82f6", "line-width": 3 },
      filter: ["==", ["get", "zone_id"], useReplayStore.getState().selectedZone ?? ""],
    })
  }, [])

  React.useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: containerRef.current, style: LIGHT_STYLE, center: [-80.3, 25.95], zoom: 8.6,
      attributionControl: { compact: true },
    })
    mapRef.current = map
    map.addControl(new maplibregl.NavigationControl(), "top-right")
    map.on("load", addLayers)
    map.on("click", "zones-fill", (e: MapLayerMouseEvent) => {
      const id = e.features?.[0]?.properties?.zone_id as string | undefined
      if (id) select(id)
    })
    map.on("mouseenter", "zones-fill", () => (map.getCanvas().style.cursor = "pointer"))
    map.on("mouseleave", "zones-fill", () => (map.getCanvas().style.cursor = ""))
    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [addLayers, select])

  // new tick or new zones: recolour in place
  React.useEffect(() => {
    dataRef.current = toGeoJSON(zones, payloads)
    const src = mapRef.current?.getSource(SOURCE_ID) as maplibregl.GeoJSONSource | undefined
    src?.setData(dataRef.current)
  }, [zones, payloads])

  React.useEffect(() => {
    const map = mapRef.current
    if (map?.getLayer("zones-selected")) map.setFilter("zones-selected", ["==", ["get", "zone_id"], selected ?? ""])
  }, [selected])

  const isDark = resolvedTheme === "dark"
  React.useEffect(() => {
    const map = mapRef.current
    if (!map) return
    map.setStyle(isDark ? DARK_STYLE : LIGHT_STYLE)
    map.once("idle", addLayers)
  }, [isDark, addLayers])

  return (
    <Card>
      <CardHeader>
        <CardTitle>High-water risk map</CardTitle>
        <CardDescription>Census places coloured by severity at the current replay time. Click a zone for details.</CardDescription>
      </CardHeader>
      <CardContent>
        <div ref={containerRef} className="h-[460px] w-full overflow-hidden rounded-lg border" />
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
        </div>
      </CardContent>
    </Card>
  )
}
