import * as React from "react"
import maplibregl, {
  type GeoJSONSource,
  type Map as MLMap,
  type MapLayerMouseEvent,
} from "maplibre-gl"
import "maplibre-gl/dist/maplibre-gl.css"
import { useTheme } from "next-themes"

import type { Coverage, Severity, Zone } from "@/api/client"
import { useRegions, useRegionZones, useRanking } from "@/api/hooks"
import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

interface ZoneProps {
  zone_id: string
  name: string
  severity: Severity | null
  probability: number | null
  is_simulated: boolean
  coverage?: Coverage
  onsetLikely?: string
  peakLikely?: string
  rankReason?: string
}

type ZoneFC = GeoJSON.FeatureCollection<GeoJSON.Polygon, ZoneProps>

const SEVERITY_COLOR: Record<Severity, string> = {
  low: "#22c55e",
  moderate: "#eab308",
  high: "#f97316",
  severe: "#ef4444",
}
const UNKNOWN_COLOR = "#9ca3af"

// Fixture zones off the Kochi coast, used only when the backend is
// unreachable. Everything here is simulated mock data, never mixed with live.
const MOCK_ZONES: ZoneFC = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: {
        zone_id: "Z-001",
        name: "Fort Kochi / Mattancherry",
        severity: "severe",
        probability: 0.91,
        is_simulated: true,
      },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [76.235, 9.955],
            [76.265, 9.955],
            [76.265, 9.985],
            [76.235, 9.985],
            [76.235, 9.955],
          ],
        ],
      },
    },
    {
      type: "Feature",
      properties: {
        zone_id: "Z-002",
        name: "Vypin Island",
        severity: "high",
        probability: 0.78,
        is_simulated: true,
      },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [76.225, 9.99],
            [76.26, 9.995],
            [76.255, 10.03],
            [76.22, 10.025],
            [76.225, 9.99],
          ],
        ],
      },
    },
    {
      type: "Feature",
      properties: {
        zone_id: "Z-003",
        name: "Kumbalam / Nettoor",
        severity: "moderate",
        probability: 0.45,
        is_simulated: true,
      },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [76.28, 9.9],
            [76.315, 9.9],
            [76.315, 9.93],
            [76.28, 9.93],
            [76.28, 9.9],
          ],
        ],
      },
    },
    {
      type: "Feature",
      properties: {
        zone_id: "Z-004",
        name: "Edakochi (inland)",
        severity: "low",
        probability: 0.12,
        is_simulated: true,
      },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [76.27, 9.925],
            [76.3, 9.925],
            [76.3, 9.955],
            [76.27, 9.955],
            [76.27, 9.925],
          ],
        ],
      },
    },
  ],
}

function toLiveFeatures(zones: Zone[]): ZoneFC {
  return {
    type: "FeatureCollection",
    features: zones.map((z) => ({
      type: "Feature",
      properties: {
        zone_id: z.id,
        name: z.name,
        severity: null,
        probability: null,
        is_simulated: z.is_simulated,
        coverage: undefined,
      },
      geometry: z.geometry,
    })),
  }
}

const LIGHT_STYLE = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
const DARK_STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"

const SOURCE_ID = "coastguard-zones"

function severityFillExpression(): maplibregl.ExpressionSpecification {
  return [
    "match",
    ["get", "severity"],
    "severe",
    SEVERITY_COLOR.severe,
    "high",
    SEVERITY_COLOR.high,
    "moderate",
    SEVERITY_COLOR.moderate,
    "low",
    SEVERITY_COLOR.low,
    UNKNOWN_COLOR,
  ]
}

function fmtTime(iso: string | undefined) {
  if (!iso) return null
  const d = new Date(iso)
  return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
}

export function RiskMap() {
  const containerRef = React.useRef<HTMLDivElement | null>(null)
  const mapRef = React.useRef<MLMap | null>(null)
  const popupRef = React.useRef<maplibregl.Popup | null>(null)
  const selectedRef = React.useRef<string | null>(null)
  const fittedRef = React.useRef(false)
  const { resolvedTheme } = useTheme()
  const [selected, setSelected] = React.useState<ZoneProps | null>(null)

  // Live data: first region's polygons joined to the ranking payloads
  // (one call for every zone's severity/probability). Any failure or empty
  // response falls back to the mock fixture below.
  const regionsQ = useRegions()
  const regionId = regionsQ.data?.[0]?.id
  const regionName = regionsQ.data?.[0]?.name
  const zonesQ = useRegionZones(regionId)
  const rankingQ = useRanking()
  const liveReady =
    zonesQ.isSuccess && zonesQ.data.length > 0 && rankingQ.isSuccess;

  const liveFeatures = React.useMemo<ZoneFC | null>(() => {
    if (!liveReady) return null
    const byId = new Map(rankingQ.data.map((p) => [p.zone_id, p]))
    return {
      type: "FeatureCollection",
      features: toLiveFeatures(zonesQ.data).features.map((f) => {
        const p = byId.get(f.properties.zone_id)
        return {
          ...f,
          properties: {
            ...f.properties,
            severity: p?.severity ?? null,
            probability: p?.probability ?? null,
            is_simulated: p?.is_simulated ?? f.properties.is_simulated,
            coverage: p?.coverage,
            onsetLikely: p?.onset?.likely,
            peakLikely: p?.peak?.likely,
            rankReason: p?.rank_reason,
          },
        }
      }),
    }
  }, [liveReady, zonesQ, rankingQ])

  const features = liveFeatures ?? MOCK_ZONES
  const dataRef = React.useRef<ZoneFC>(features)
  dataRef.current = features

  const applySelectedFilter = React.useCallback(() => {
    const map = mapRef.current
    if (!map || map.getLayer("zones-selected") == null) return
    map.setFilter("zones-selected", [
      "==",
      ["get", "zone_id"],
      selectedRef.current ?? "",
    ])
  }, [])

  const addZoneLayers = React.useCallback(() => {
    const map = mapRef.current
    if (!map || map.getSource(SOURCE_ID) != null) return

    map.addSource(SOURCE_ID, { type: "geojson", data: dataRef.current })

    map.addLayer({
      id: "zones-fill",
      type: "fill",
      source: SOURCE_ID,
      paint: {
        "fill-color": severityFillExpression(),
        "fill-opacity": 0.45,
      },
    })
    map.addLayer({
      id: "zones-outline",
      type: "line",
      source: SOURCE_ID,
      paint: {
        "line-color": severityFillExpression(),
        "line-width": 1.5,
      },
    })
    map.addLayer({
      id: "zones-selected",
      type: "line",
      source: SOURCE_ID,
      paint: {
        "line-color": "#ffffff",
        "line-width": 3,
      },
      filter: ["==", ["get", "zone_id"], selectedRef.current ?? ""],
    })
  }, [])

  // Init once.
  React.useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: LIGHT_STYLE,
      center: [76.27, 9.965],
      zoom: 11,
      attributionControl: { compact: true },
    })
    mapRef.current = map
    map.addControl(new maplibregl.NavigationControl(), "top-right")

    map.on("load", () => {
      addZoneLayers()
    })

    map.on("click", "zones-fill", (e: MapLayerMouseEvent) => {
      const feature = e.features?.[0]
      if (!feature) return
      const props = feature.properties as ZoneProps
      selectedRef.current = props.zone_id
      setSelected(props)
      applySelectedFilter()

      const sev = props.severity ?? "unknown"
      const prob =
        props.probability == null ? "unknown" : `P(flood): <strong>${props.probability.toFixed(2)}</strong>`
      const onset = fmtTime(props.onsetLikely)
      const peak = fmtTime(props.peakLikely)
      const timing =
        onset && peak ? `<br/>Onset ${onset} · peak ${peak}` : ""
      const simBadge = props.is_simulated
        ? `<span style="display:inline-block;margin-top:4px;padding:1px 6px;border-radius:9999px;background:#fef3c7;color:#92400e;font-size:11px;">Simulation</span>`
        : ""

      popupRef.current?.remove()
      popupRef.current = new maplibregl.Popup({ closeOnClick: true })
        .setLngLat(e.lngLat)
        .setHTML(
          `<div style="font: 12px/1.5 system-ui, sans-serif; color: #111;">` +
            `<strong>${props.zone_id} · ${props.name}</strong><br/>` +
            `Severity: <strong>${sev}</strong> · ${prob}${timing}<br/>` +
            simBadge +
            `</div>`
        )
        .addTo(map)
    })

    map.on("mouseenter", "zones-fill", () => {
      map.getCanvas().style.cursor = "pointer"
    })
    map.on("mouseleave", "zones-fill", () => {
      map.getCanvas().style.cursor = ""
    })

    return () => {
      popupRef.current?.remove()
      map.remove()
      mapRef.current = null
    }
  }, [addZoneLayers, applySelectedFilter])

  // Push new data into the source; fit the camera once live polygons arrive.
  React.useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const src = map.getSource(SOURCE_ID) as GeoJSONSource | undefined
    if (src) src.setData(features)
    if (liveFeatures && !fittedRef.current && liveFeatures.features.length > 0) {
      const bounds = new maplibregl.LngLatBounds()
      for (const f of liveFeatures.features) {
        for (const ring of f.geometry.coordinates) {
          for (const [lng, lat] of ring) bounds.extend([lng, lat])
        }
      }
      if (!bounds.isEmpty()) {
        map.fitBounds(bounds, { padding: 40, maxZoom: 12 })
        fittedRef.current = true
      }
    }
  }, [features, liveFeatures])

  // Follow light/dark toggle by swapping the basemap, then re-adding zones.
  const isDark = resolvedTheme === "dark"
  React.useEffect(() => {
    const map = mapRef.current
    if (!map) return
    map.setStyle(isDark ? DARK_STYLE : LIGHT_STYLE)
    map.once("idle", () => {
      addZoneLayers()
      const src = map.getSource(SOURCE_ID) as GeoJSONSource | undefined
      if (src) src.setData(dataRef.current)
      applySelectedFilter()
    })
  }, [isDark, addZoneLayers, applySelectedFilter])

  const hasUnknown = features.features.some((f) => f.properties.severity == null)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Flood-risk map</CardTitle>
        <CardDescription>
          Neighbourhood zones coloured by severity. Click a zone for details.
        </CardDescription>
        <CardAction>
          {liveFeatures ? (
            <Badge variant="outline">Live · {regionName}</Badge>
          ) : (
            <Badge variant="outline">Simulation · mock data</Badge>
          )}
        </CardAction>
      </CardHeader>
      <CardContent>
        <div
          ref={containerRef}
          className="h-[420px] w-full overflow-hidden rounded-lg border"
        />
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted-foreground">
          {(Object.keys(SEVERITY_COLOR) as Severity[]).map((s) => (
            <span key={s} className="inline-flex items-center gap-1.5">
              <span
                className="inline-block size-3 rounded-sm"
                style={{ backgroundColor: SEVERITY_COLOR[s] }}
              />
              {s}
            </span>
          ))}
          {hasUnknown && (
            <span className="inline-flex items-center gap-1.5">
              <span
                className="inline-block size-3 rounded-sm"
                style={{ backgroundColor: UNKNOWN_COLOR }}
              />
              unknown
            </span>
          )}
          {selected != null && (
            <span className="ml-auto font-medium text-foreground">
              {selected.zone_id} · {selected.name} · {selected.severity ?? "unknown"} ·{" "}
              {selected.probability == null ? "P unknown" : `P=${selected.probability.toFixed(2)}`}
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
