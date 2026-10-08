import * as React from "react"

import { useEvents, useReplayData } from "@/api/hooks"
import { useAlertToasts } from "@/components/alert-feed"
import { AppShell } from "@/components/app-shell"
import { DashboardMode } from "@/components/dashboard-mode"
import { HazardArticles } from "@/components/hazard-articles"
import { LiveHazard } from "@/components/live-hazard"
import { RiskMap } from "@/components/risk-map"
import { SectionCards } from "@/components/section-cards"
import { TimeSlider } from "@/components/time-slider"
import { ZonePanel } from "@/components/zone-panel"
import { useReplayStore } from "@/state/replayStore"

export default function Dashboard() {
  const selectedZone = useReplayStore((s) => s.selectedZone)
  const live = useReplayStore((s) => s.mode) === "live"
  const events = useEvents()
  // fixed default weights here; tuning happens only on the Response priority page
  const { region, zones, ticks, now, names, rows, feed, error } = useReplayData()
  useAlertToasts(live ? [] : feed, names, now) // the full feed lives on the Alerts page

  // Esc clears the selected zone
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && useReplayStore.getState().select(null)
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  return (
    <AppShell>
      <div className="@container/main flex flex-1 flex-col gap-4 py-4 md:gap-6 md:py-6">
        <div className="px-4 lg:px-6">
          <DashboardMode events={events.data ?? []} />
        </div>
        {!live && error && (
          <div className="mx-4 rounded-md border border-destructive p-3 text-sm text-destructive lg:mx-6">
            Backend error: {String(error)}. Is the API running on port 8000?
          </div>
        )}
        <div className="grid grid-cols-1 items-start gap-4 px-4 lg:px-6 @5xl/main:grid-cols-[2fr_1fr]">
          <div className="flex flex-col gap-4">
            <RiskMap zones={zones} payloads={rows} live={live} />
            {!live && <TimeSlider ticks={ticks} />}
          </div>
          {live ? (
            <LiveHazard />
          ) : (
            <ZonePanel zone={rows.find((p) => p.zone_id === selectedZone)} name={selectedZone ? names.get(selectedZone) : undefined} />
          )}
        </div>
        {live ? (
          <div className="px-4 lg:px-6">
            <HazardArticles />
          </div>
        ) : (
          <SectionCards payloads={rows} region={region} />
        )}
      </div>
    </AppShell>
  )
}
