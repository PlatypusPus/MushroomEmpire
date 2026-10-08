import * as React from "react"
import * as L from "leaflet"
import { useMap } from "react-leaflet"

import { useEnvLayers } from "@/api/hooks"
import { useMapToggles } from "@/state/mapLayersStore"

const FRAME_MS = 600

/** Animated RainViewer radar loop (past frames), z-ordered above zone fills. Toggles: radar (+ radarPlaying). */
export function RadarOverlay() {
  const map = useMap()
  const on = useMapToggles((s) => s.radar)
  const playing = useMapToggles((s) => s.radarPlaying)
  const { data } = useEnvLayers()
  const layersRef = React.useRef<L.TileLayer[]>([])
  const timerRef = React.useRef<ReturnType<typeof setInterval> | null>(null)

  React.useEffect(() => {
    const teardown = () => {
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
      layersRef.current.forEach((l) => l.remove())
      layersRef.current = []
    }
    teardown()

    const frames = data?.radar.frames ?? []
    if (!on || !data || frames.length === 0) return

    if (!map.getPane("radarPane")) {
      const pane = map.createPane("radarPane")
      pane.style.zIndex = "450" // above zone fills (400), below markers (600)
      pane.style.pointerEvents = "none"
    }
    // One layer per frame, all loaded up front, and the animation only swaps opacity. (Swapping a single layer's url every
    // 600 ms cancelled every tile before it finished loading, so the radar flickered and mostly never drew.)
    // RainViewer only serves radar up to zoom 7; deeper zooms return a "zoom level not supported" picture tile,
    // so maxNativeZoom makes Leaflet stretch the zoom-7 tiles instead of requesting those placeholders.
    const layers = frames.map((f) =>
      L.tileLayer(`${data.radar.host}${f.path}/256/{z}/{x}/{y}/${data.radar.color}/${data.radar.options}.png`, {
        pane: "radarPane", opacity: 0, attribution: "RainViewer", maxNativeZoom: 7, keepBuffer: 1,
      }).addTo(map),
    )
    layersRef.current = layers
    let i = layers.length - 1 // newest frame first
    const show = (k: number) => layers.forEach((l, j) => l.setOpacity(j === k ? 0.55 : 0))
    show(i)
    if (playing && layers.length > 1) {
      timerRef.current = setInterval(() => {
        i = (i + 1) % layers.length
        show(i)
      }, FRAME_MS)
    }
    return teardown
  }, [on, playing, data, map])

  return null
}
