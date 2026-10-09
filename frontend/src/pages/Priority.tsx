import * as React from "react"

import { useEvents, useLivePriority, useReplayData } from "@/api/hooks"
import { AppShell } from "@/components/app-shell"
import { LiveHazard } from "@/components/live-hazard"
import { RankingQueue } from "@/components/ranking-queue"
import { RiskMap } from "@/components/risk-map"
import { ZonePanel } from "@/components/zone-panel"
import { useReplayStore } from "@/state/replayStore"

/** Response priority: the one place ranking weights can be tuned. The dashboard always ranks with the defaults.
 * Storm replay ranks a past storm; Live ranks right now from our experimental forecast at each place's nearest live gauge. */
export default function Priority() {
  const selectedZone = useReplayStore((s) => s.selectedZone)
  const live = useReplayStore((s) => s.mode) === "live"
  const weights = useReplayStore((s) => s.weights)
  const events = useEvents()
  const replay = useReplayData({ tunable: true })
  const lp = useLivePriority(weights, live)
  const rows = live ? (lp.data?.rows ?? []) : replay.rows
  const { zones, ticks, names } = replay
  const error = live ? lp.error : replay.error

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
        {live && (
          <div className="mx-4 rounded-lg border border-dashed p-3 text-sm lg:mx-6">
            <span className="font-semibold">Live ranking · experimental.</span>{" "}
            Each place is ranked from our forecast at its nearest live USGS water gauge, from the model that keeps learning. It has not been
            validated live; places with no gauge nearby are listed last as unknown.
            {lp.data?.status === "computing" && (
              <span className="mt-2 block">
                <span className="font-medium">Checking live gauges: {lp.data.done} of {lp.data.total} places.</span>{" "}
                {lp.data.issued ? "Showing the last ranking meanwhile." : "The first run downloads each gauge's history and takes a few minutes."}
                <span className="mt-1.5 block h-1.5 w-full overflow-hidden rounded-full bg-muted">
                  <span className="block h-full rounded-full bg-primary transition-all" style={{ width: `${(100 * lp.data.done) / Math.max(1, lp.data.total)}%` }} />
                </span>
              </span>
            )}
            {lp.data?.issued && lp.data.status === "ready" && (
              <span className="mt-1 block text-xs text-muted-foreground">Updated {new Date(lp.data.issued).toLocaleTimeString()} · refreshes every 15 minutes</span>
            )}
          </div>
        )}
        <div className="grid grid-cols-1 items-start gap-4 px-4 lg:px-6 @5xl/main:grid-cols-[3fr_2fr]">
          <div className="flex flex-col gap-4">
            <RiskMap zones={zones} payloads={rows} events={events.data ?? []} ticks={ticks} live={live} rankedLive />
            <ZonePanel zone={rows.find((p) => p.zone_id === selectedZone)} name={selectedZone ? names.get(selectedZone) : undefined} tunable />
          </div>
          <div className="flex flex-col gap-4">
            <RankingQueue payloads={rows} names={names} />
            {/* live: the official picture beside our experimental ranking */}
            {live && <div className="shrink-0"><LiveHazard /></div>}
          </div>
        </div>
      </div>
    </AppShell>
  )
}
