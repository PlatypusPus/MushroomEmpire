import * as React from "react"
import { PauseIcon, PlayIcon } from "lucide-react"

import { clock } from "@/api/client"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { useReplayStore } from "@/state/replayStore"

const TICK_MS = 1000

export function TimeSlider({ ticks, eventName }: { ticks: string[]; eventName: string }) {
  const { tick, playing, setTick, setPlaying } = useReplayStore()

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
          <div className="text-xs text-muted-foreground">
            {eventName} · replay of held-out data · gauge clock, timezone unverified
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
