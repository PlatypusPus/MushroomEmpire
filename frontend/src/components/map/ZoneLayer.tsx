import * as React from "react"
import * as L from "leaflet"
import { useMap } from "react-leaflet"

import { SEVERITY_COLOR, UNKNOWN_COLOR, type Zone, type ZonePayload } from "@/api/client"
import { useMapToggles } from "@/state/mapLayersStore"
import { useReplayStore } from "@/state/replayStore"

const SELECT_RING = "#3b82f6"

function severityColor(sev: ZonePayload["severity"] | undefined): string {
  return sev ? SEVERITY_COLOR[sev] : UNKNOWN_COLOR
}

type FeatureLayer = L.Layer & { feature?: GeoJSON.Feature }

function zoneIdOf(l: L.Layer): string | undefined {
  const props = (l as FeatureLayer).feature?.properties as { zone_id?: string } | undefined
  return props?.zone_id
}

function tooltipText(name: string, p: ZonePayload | undefined): string {
  if (!p) return `${name} · insufficient data`
  const sev = p.severity ?? "insufficient data"
  const prob = p.probability == null ? "n/a" : `${Math.round(p.probability * 100)}%`
  return `${name} · ${sev} · ${prob}${p.is_alert ? " · ON ALERT" : ""}`
}

/** Zone polygons as a single imperative GeoJSON layer (in-place setStyle keeps
 * CSS fill transitions alive across replay ticks). Toggles: zones, pulse,
 * spotlight, transitions. */
export function ZoneLayer({ zones, payloads }: { zones: Zone[]; payloads: ZonePayload[] }) {
  const map = useMap()
  const selected = useReplayStore((s) => s.selectedZone)
  const select = useReplayStore((s) => s.select)
  const zonesOn = useMapToggles((s) => s.zones)
  const pulseOn = useMapToggles((s) => s.pulse)
  const spotlightOn = useMapToggles((s) => s.spotlight)
  const transitionsOn = useMapToggles((s) => s.transitions)

  const layerRef = React.useRef<L.GeoJSON | null>(null)
  const idsRef = React.useRef<string>("")
  const stateRef = React.useRef({ zones, payloads, selected, pulseOn, spotlightOn, transitionsOn })
  stateRef.current = { zones, payloads, selected, pulseOn, spotlightOn, transitionsOn }
  const skipDeselect = React.useRef(false)

  const styleFor = React.useCallback((zoneId: string): L.PathOptions => {
    const { payloads: pl, selected: sel } = stateRef.current
    const p = pl.find((x) => x.zone_id === zoneId)
    const c = severityColor(p?.severity)
    const isSel = sel === zoneId
    return {
      fillColor: c,
      fillOpacity: 0.5,
      color: isSel ? SELECT_RING : c,
      weight: isSel ? 3 : 1,
      opacity: 1,
    }
  }, [])

  const applyClasses = React.useCallback((layer: L.Layer, zoneId: string) => {
    const { payloads: pl, pulseOn: pu, spotlightOn: sp, transitionsOn: tr } = stateRef.current
    const el = (layer as L.Path).getElement?.()
    if (!el) return
    const p = pl.find((x) => x.zone_id === zoneId)
    el.classList.add("zone-path")
    el.classList.toggle("zone-no-anim", !tr)
    el.classList.toggle("zone-alert", pu && !!p?.is_alert)
    el.classList.toggle("zone-spot", sp && p?.rank === 1)
  }, [])

  // create once
  React.useEffect(() => {
    const geo = L.geoJSON(undefined, {
      style: (f) => styleFor((f?.properties as { zone_id: string } | undefined)?.zone_id ?? ""),
      onEachFeature: (f, layer) => {
        const zoneId = (f.properties as { zone_id: string; name: string }).zone_id
        const name = (f.properties as { zone_id: string; name: string }).name
        layer.bindTooltip(() => tooltipText(name, stateRef.current.payloads.find((x) => x.zone_id === zoneId)), {
          sticky: true,
          direction: "top",
        })
        layer.on("click", () => {
          skipDeselect.current = true
          select(zoneId)
        })
        layer.on("mouseover", () => {
          map.getContainer().style.cursor = "pointer"
        })
        layer.on("mouseout", () => {
          map.getContainer().style.cursor = ""
        })
      },
    })
    layerRef.current = geo
    if (useMapToggles.getState().zones) geo.addTo(map)
    const onMapClick = () => {
      if (skipDeselect.current) {
        skipDeselect.current = false
        return
      }
      select(null)
    }
    map.on("click", onMapClick)
    return () => {
      map.off("click", onMapClick)
      map.getContainer().style.cursor = ""
      geo.remove()
      layerRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map])

  const sync = React.useCallback(() => {
    const geo = layerRef.current
    if (!geo) return
    const ids = zones.map((z) => z.id).join(",")
    if (ids !== idsRef.current) {
      // zone set changed (event switch): full rebuild
      idsRef.current = ids
      geo.clearLayers()
      geo.addData({
        type: "FeatureCollection",
        features: zones.map((z) => ({
          type: "Feature",
          geometry: z.geometry,
          properties: { zone_id: z.id, name: z.name },
        })),
      } as GeoJSON.FeatureCollection)
    }
    geo.eachLayer((l) => {
      const zoneId = zoneIdOf(l)
      if (!zoneId) return
      ;(l as L.Path).setStyle(styleFor(zoneId))
      applyClasses(l, zoneId)
    })
    const sel = stateRef.current.selected
    if (sel) {
      geo.eachLayer((l) => {
        if (zoneIdOf(l) === sel) (l as L.Path).bringToFront()
      })
    }
  }, [zones, styleFor, applyClasses])

  // data / selection / animation toggles: restyle in place (transitions animate)
  React.useEffect(() => {
    sync()
  }, [sync, payloads, selected, pulseOn, spotlightOn, transitionsOn])

  // zones master toggle: attach/detach
  React.useEffect(() => {
    const geo = layerRef.current
    if (!geo) return
    if (zonesOn) {
      geo.addTo(map)
      sync()
    } else {
      geo.remove()
    }
  }, [zonesOn, map, sync])

  return null
}
