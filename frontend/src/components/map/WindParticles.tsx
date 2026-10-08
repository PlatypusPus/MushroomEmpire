import * as React from "react"
import * as L from "leaflet"
import { useMap } from "react-leaflet"

import type { EnvLayers } from "@/api/client"
import { useEnvLayers } from "@/api/hooks"
import { useMapToggles } from "@/state/mapLayersStore"

type Wind = NonNullable<EnvLayers["wind"]>

const COUNT = 220
const EXAGGERATE = 260 // visual speed multiplier: real wind is far too slow to see
const MAX_AGE = 90 // frames before a particle respawns

interface Particle {
  lat: number
  lon: number
  age: number
}

function sampleWind(w: Wind, lat: number, lon: number): { sp: number; dr: number } | null {
  const { lats, lons, speed_kmh, dir_deg } = w
  if (lat < lats[0] || lat > lats[lats.length - 1] || lon < lons[0] || lon > lons[lons.length - 1]) return null
  const fi = lats.findIndex((t) => t > lat) - 1
  const ci = lons.findIndex((t) => t > lon) - 1
  const r0 = Math.max(0, fi === -2 ? lats.length - 2 : fi)
  const c0 = Math.max(0, ci === -2 ? lons.length - 2 : ci)
  const r1 = Math.min(lats.length - 1, r0 + 1)
  const c1 = Math.min(lons.length - 1, c0 + 1)
  const fr = (lat - lats[r0]) / Math.max(1e-9, lats[r1] - lats[r0])
  const fc = (lon - lons[c0]) / Math.max(1e-9, lons[c1] - lons[c0])
  const mix = (a: number, b: number, c: number, d: number) => a * (1 - fr) * (1 - fc) + b * fr * (1 - fc) + c * (1 - fr) * fc + d * fr * fc
  return {
    sp: mix(speed_kmh[r0][c0], speed_kmh[r1][c0], speed_kmh[r0][c1], speed_kmh[r1][c1]),
    dr: mix(dir_deg[r0][c0], dir_deg[r1][c0], dir_deg[r0][c1], dir_deg[r1][c1]),
  }
}

function spawn(w: Wind): Particle {
  const { lats, lons } = w
  return {
    lat: lats[0] + Math.random() * (lats[lats.length - 1] - lats[0]),
    lon: lons[0] + Math.random() * (lons[lons.length - 1] - lons[0]),
    age: Math.floor(Math.random() * MAX_AGE),
  }
}

/** Animated surface-wind particles on a canvas pane, advected over the Open-Meteo wind grid. Toggle: wind. */
export function WindParticles() {
  const map = useMap()
  const on = useMapToggles((s) => s.wind)
  const { data } = useEnvLayers()
  const partsRef = React.useRef<Particle[]>([])

  React.useEffect(() => {
    const wind = data?.wind
    if (!on || !wind) return

    if (!map.getPane("windPane")) {
      const pane = map.createPane("windPane")
      pane.style.zIndex = "460" // above radar (450), below markers (600)
      pane.style.pointerEvents = "none"
    }
    const canvas = document.createElement("canvas")
    canvas.style.position = "absolute"
    canvas.style.top = "0"
    canvas.style.left = "0"
    canvas.style.pointerEvents = "none"
    map.getPane("windPane")!.appendChild(canvas)
    const ctx = canvas.getContext("2d")

    const resize = () => {
      const size = map.getSize()
      canvas.width = size.x
      canvas.height = size.y
      L.DomUtil.setPosition(canvas, map.containerPointToLayerPoint([0, 0]))
    }
    resize()
    map.on("resize moveend zoomend viewreset", resize)

    partsRef.current = Array.from({ length: COUNT }, () => spawn(wind))
    let raf = 0
    let last = performance.now()

    const frame = (ts: number) => {
      raf = requestAnimationFrame(frame)
      if (!ctx) return
      const dt = Math.min(0.1, (ts - last) / 1000)
      last = ts
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      ctx.lineWidth = 1.8
      ctx.strokeStyle = "rgba(56, 189, 248, 0.65)"
      ctx.beginPath()
      for (const p of partsRef.current) {
        const s = sampleWind(wind, p.lat, p.lon)
        p.age += 1
        if (!s || p.age > MAX_AGE) {
          Object.assign(p, spawn(wind))
          continue
        }
        const from = map.latLngToContainerPoint([p.lat, p.lon])
        const to = ((s.dr + 180) * Math.PI) / 180 // meteorological "from" -> direction of travel
        const stepH = ((s.sp * dt) / 3600) * EXAGGERATE // km/h -> exaggerated degrees-of-travel per frame
        p.lat += (Math.cos(to) * stepH) / 111 // north component (deg lat)
        p.lon += Math.sin(to) * stepH / (111 * Math.cos((p.lat * Math.PI) / 180)) // east component (deg lon)
        const toPt = map.latLngToContainerPoint([p.lat, p.lon])
        ctx.moveTo(from.x, from.y)
        ctx.lineTo(toPt.x, toPt.y)
      }
      ctx.stroke()
    }
    raf = requestAnimationFrame(frame)

    return () => {
      cancelAnimationFrame(raf)
      map.off("resize moveend zoomend viewreset", resize)
      canvas.remove()
      partsRef.current = []
    }
  }, [on, data, map])

  return null
}
