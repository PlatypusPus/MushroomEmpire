import { CircleMarker, useMapEvents } from "react-leaflet"

import { useReplayStore } from "@/state/replayStore"

/** Live map: a click anywhere asks for advice at that spot. Storms do not stop at the edge of the places we cover. */
export function LivePointPicker() {
  const point = useReplayStore((s) => s.livePoint)
  const setPoint = useReplayStore((s) => s.setLivePoint)
  useMapEvents({ click: (e) => setPoint({ lat: e.latlng.lat, lon: e.latlng.lng }) })
  return point ? (
    <CircleMarker center={[point.lat, point.lon]} radius={7} pathOptions={{ color: "#3b82f6", weight: 3, fillOpacity: 0.4 }} interactive={false} />
  ) : null
}
