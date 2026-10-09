import { GeoJSON, Pane } from "react-leaflet"

import { useWaterSpread } from "@/api/hooks"
import { useMapToggles } from "@/state/mapLayersStore"
import { useReplayStore } from "@/state/replayStore"

/** 2D replay: blue wash around flooding places where their water may spread. Own pane just above the place colours
 * (under them it would be hidden); non-interactive, so clicks still reach the places. */
export function SpillLayer({ issueTs }: { issueTs: string | undefined }) {
  const eventId = useReplayStore((s) => s.eventId)
  const on = useMapToggles((s) => s.zones)
  const q = useWaterSpread(eventId, issueTs)
  if (!on || !q.data) return null
  return (
    <Pane name="spill" style={{ zIndex: 410, pointerEvents: "none" }}>
      {/* GeoJSON does not diff its data prop: a new key per step redraws it */}
      <GeoJSON key={`${eventId}-${issueTs}`} data={q.data.spill_geo} interactive={false}
        style={(f) => ({ color: "#1d4ed8", weight: 1.5, dashArray: "4 3", fillColor: "#2563eb", fillOpacity: 0.5 * ((f?.properties as { probability?: number })?.probability ?? 0.5) })} />
    </Pane>
  )
}
