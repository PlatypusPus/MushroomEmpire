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
  const layerRef = React.useRef<L.TileLayer | null>(null)
  const timerRef = React.useRef<ReturnType<typeof setInterval> | null>(null)

  React.useEffect(() => {
    const teardown = () => {
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
      layerRef.current?.remove()
      layerRef.current = null
    }
    teardown()

    const frames = data?.radar.frames ?? []
    if (!on || !data || frames.length === 0) return

    if (!map.getPane("radarPane")) {
      const pane = map.createPane("radarPane")
      pane.style.zIndex = "450" // above zone fills (400), below markers (600)
      pane.style.pointerEvents = "none"
    }
    const url = (i: number) =>
      `${data.radar.host}${frames[i].path}/256/{z}/{x}/{y}/${data.radar.color}/${data.radar.options}.png`
    let i = 0
    const layer = L.tileLayer(url(0), { pane: "radarPane", opacity: 0.55, attribution: "RainViewer" })
    layer.addTo(map)
    layerRef.current = layer
    if (playing && frames.length > 1) {
      timerRef.current = setInterval(() => {
        i = (i + 1) % frames.length
        layer.setUrl(url(i))
      }, FRAME_MS)
    }
    return teardown
  }, [on, playing, data, map])

  return null
}
