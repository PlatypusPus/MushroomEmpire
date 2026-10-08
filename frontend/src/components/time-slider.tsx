import * as React from "react"
import { PauseIcon, PlayIcon } from "lucide-react"

import { clock, type CoastEvent } from "@/api/client"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { useReplayStore } from "@/state/replayStore"

const TICK_MS = 1000

/** `events` is optional: pages that already have an event picker (the dashboard) leave it out. */
export function TimeSlider({ ticks, events }: { ticks: string[]; events?: CoastEvent[] }) {
  const { tick, playing, setTick, setPlaying, eventId, setEvent } = useReplayStore()

  React.useEffect(() => {
    if (!playing) return
    const id = setInterval(() => {
      const s = useReplayStore.getState()
      if (s.tick >= ticks.length - 1) s.setPlaying(false)
      else s.setTick(s.tick + 1)
    }, TICK_MS)
    return () => clearInterval(id)
  }, [playing, ticks.length])

  const now = ticks[tick]
  return (
    <Card>
      <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <Button size="sm" onClick={() => setPlaying(!playing)} aria-label={playing ? "Pause replay" : "Play replay"}>
          {playing ? <PauseIcon /> : <PlayIcon />}
          {playing ? "Pause" : "Play"}
        </Button>
        <input
          type="range" min={0} max={Math.max(ticks.length - 1, 0)} value={tick}
          onChange={(e) => setTick(+e.target.value)} className="flex-1 accent-primary" aria-label="Replay time"
        />
        <div className="text-sm tabular-nums">
          <div className="font-medium">{now ? clock(now, true) : "..."}</div>
          {events && (
          <select
            value={eventId}
            onChange={(e) => setEvent(+e.target.value)}
            className="mt-0.5 max-w-64 rounded-md border bg-background px-1.5 py-0.5 text-xs"
            aria-label="Storm to replay"
          >
            {events.map((ev) => (
              <option key={ev.id} value={ev.id}>
                {ev.name}{ev.is_holdout ? " (test storm)" : ""}
              </option>
            ))}
            {!events.some((ev) => ev.id === eventId) && <option value={eventId}>Event {eventId}</option>}
          </select>
          )}
          <div className="text-xs text-muted-foreground">replay of past storm data · times may be off by a few hours</div>
        </div>
      </CardContent>
    </Card>
  )
}
