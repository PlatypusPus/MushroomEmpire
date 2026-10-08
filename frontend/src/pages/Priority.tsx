import * as React from "react"

import { useEvents, useReplayData } from "@/api/hooks"
import { AppShell } from "@/components/app-shell"
import { RankingQueue } from "@/components/ranking-queue"
import { RiskMap } from "@/components/risk-map"
import { ZonePanel } from "@/components/zone-panel"
import { useReplayStore } from "@/state/replayStore"

/** Response priority: the one place ranking weights can be tuned. The dashboard always ranks with the defaults. */
export default function Priority() {
  const selectedZone = useReplayStore((s) => s.selectedZone)
  const events = useEvents()
  const { zones, ticks, names, rows, error } = useReplayData({ tunable: true })

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && useReplayStore.getState().select(null)
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  return (
    <AppShell>
      <div className="@container/main flex flex-1 flex-col gap-4 py-4 md:gap-6 md:py-6">
        {error && (
          <div className="mx-4 rounded-md border border-destructive p-3 text-sm text-destructive lg:mx-6">Backend error: {String(error)}</div>
        )}
        <div className="grid grid-cols-1 items-start gap-4 px-4 lg:px-6 @5xl/main:grid-cols-[3fr_2fr]">
          <div className="flex flex-col gap-4">
            <RiskMap zones={zones} payloads={rows} events={events.data ?? []} ticks={ticks} />
            <ZonePanel zone={rows.find((p) => p.zone_id === selectedZone)} name={selectedZone ? names.get(selectedZone) : undefined} tunable />
          </div>
          <RankingQueue payloads={rows} names={names} />
        </div>
      </div>
    </AppShell>
  )
}
