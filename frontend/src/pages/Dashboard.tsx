import * as React from "react"

import { useAlertFeed, useEvents, useRegionZones, useRegions, useReplay, useTick } from "@/api/hooks"
import { AlertFeed } from "@/components/alert-feed"
import { AppShell } from "@/components/app-shell"
import { RankingQueue } from "@/components/ranking-queue"
import { RiskMap } from "@/components/risk-map"
import { SectionCards } from "@/components/section-cards"
import { TimeSlider } from "@/components/time-slider"
import { ZonePanel } from "@/components/zone-panel"
import { useReplayStore } from "@/state/replayStore"

const STEP_H = 3 // replay frame every 3 h of the event

export default function Dashboard() {
  const { eventId, tick, weights, selectedZone } = useReplayStore()
  const events = useEvents()
  const regions = useRegions(eventId)
  const region = regions.data?.[0]
  const zones = useRegionZones(region?.id, eventId)
  const replay = useReplay(eventId, STEP_H)
  const ticks = replay.data?.ticks ?? []
  const payloads = useTick(eventId, ticks[tick], weights)
  const alerts = useAlertFeed(replay.data?.session_id, tick)

  // Esc clears the selected zone
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && useReplayStore.getState().select(null)
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  const names = React.useMemo(() => new Map((zones.data ?? []).map((z) => [z.id, z.name])), [zones.data])
  const event = events.data?.find((e) => e.id === eventId)
  const rows = payloads.data ?? []
  const error = [regions, zones, replay, payloads].find((q) => q.error)?.error

  return (
    <AppShell>
      <div className="@container/main flex flex-1 flex-col gap-4 py-4 md:gap-6 md:py-6">
        {error && (
          <div className="mx-4 rounded-md border border-destructive p-3 text-sm text-destructive lg:mx-6">
            Backend error: {String(error)}. Is the API running on port 8000?
          </div>
        )}
        <SectionCards payloads={rows} region={region} />
        <div className="px-4 lg:px-6">
          <TimeSlider ticks={ticks} eventName={event?.name ?? `Event ${eventId}`} />
        </div>
        <div className="grid grid-cols-1 gap-4 px-4 lg:px-6 @5xl/main:grid-cols-[2fr_1fr]">
          <RiskMap zones={zones.data ?? []} payloads={rows} />
          <div className="flex flex-col gap-4">
            <AlertFeed feed={alerts.data ?? []} names={names} now={ticks[tick]} />
            <ZonePanel zone={rows.find((p) => p.zone_id === selectedZone)} name={selectedZone ? names.get(selectedZone) : undefined} />
          </div>
        </div>
        <div className="px-4 lg:px-6">
          <RankingQueue payloads={rows} names={names} />
        </div>
      </div>
    </AppShell>
  )
}
