import * as React from "react"

import { useEvents, useRegion, useReplay, useTick, useZones } from "@/api/client"
import { AppSidebar } from "@/components/app-sidebar"
import { RankingQueue } from "@/components/ranking-queue"
import { RiskMap } from "@/components/risk-map"
import { SectionCards } from "@/components/section-cards"
import { SiteHeader } from "@/components/site-header"
import { TimeSlider } from "@/components/time-slider"
import { ZonePanel } from "@/components/zone-panel"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { useReplayStore } from "@/state/replayStore"

const STEP_H = 3 // replay frame every 3 h of the event

export default function Dashboard() {
  const { eventId, tick, weights, selectedZone } = useReplayStore()
  const events = useEvents()
  const region = useRegion(eventId)
  const zones = useZones(region.data?.id, eventId)
  const replay = useReplay(eventId, STEP_H)
  const ticks = replay.data?.ticks ?? []
  const payloads = useTick(eventId, ticks[tick], weights)

  const names = React.useMemo(() => new Map((zones.data ?? []).map((z) => [z.id, z.name])), [zones.data])
  const event = events.data?.find((e) => e.id === eventId)
  const rows = payloads.data ?? []
  const error = [region, zones, replay, payloads].find((q) => q.error)?.error

  return (
    <TooltipProvider>
      <SidebarProvider
        style={{ "--sidebar-width": "calc(var(--spacing) * 72)", "--header-height": "calc(var(--spacing) * 12)" } as React.CSSProperties}
      >
        <AppSidebar variant="inset" />
        <SidebarInset>
          <SiteHeader />
          <div className="@container/main flex flex-1 flex-col gap-4 py-4 md:gap-6 md:py-6">
            {error && (
              <div className="mx-4 rounded-md border border-destructive p-3 text-sm text-destructive lg:mx-6">
                Backend error: {String(error)}. Is the API running on port 8000?
              </div>
            )}
            <SectionCards payloads={rows} region={region.data} />
            <div className="px-4 lg:px-6">
              <TimeSlider ticks={ticks} eventName={event?.name ?? `Event ${eventId}`} />
            </div>
            <div className="grid grid-cols-1 gap-4 px-4 lg:px-6 @5xl/main:grid-cols-[2fr_1fr]">
              <RiskMap zones={zones.data ?? []} payloads={rows} />
              <ZonePanel zone={rows.find((p) => p.zone_id === selectedZone)} name={selectedZone ? names.get(selectedZone) : undefined} />
            </div>
            <div className="px-4 lg:px-6">
              <RankingQueue payloads={rows} names={names} />
            </div>
          </div>
        </SidebarInset>
      </SidebarProvider>
      <Toaster />
    </TooltipProvider>
  )
}
