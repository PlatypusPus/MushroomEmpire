// Dashboard mode: Live (official NWS and NHC hazards now) or Storm replay (the flood model on a past event, pick the event here).
// The flood model has no live gauge feed yet, so its forecasts exist only for replays. The live view says so instead of faking one.
import { RadioIcon, RewindIcon } from "lucide-react"

import type { CoastEvent } from "@/api/client"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { useReplayStore } from "@/state/replayStore"

export function DashboardMode({ events }: { events: CoastEvent[] }) {
  const { mode, setMode, eventId, setEvent } = useReplayStore()
  return (
    <Card>
      <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="inline-flex rounded-lg border p-0.5" role="group" aria-label="Dashboard mode">
          <Button size="sm" variant={mode === "live" ? "default" : "ghost"} aria-pressed={mode === "live"} onClick={() => setMode("live")} className="gap-1.5">
            <RadioIcon className="size-3.5" /> Live now
          </Button>
          <Button size="sm" variant={mode === "replay" ? "default" : "ghost"} aria-pressed={mode === "replay"} onClick={() => setMode("replay")} className="gap-1.5">
            <RewindIcon className="size-3.5" /> Storm replay
          </Button>
        </div>
        {mode === "replay" ? (
          <label className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Event</span>
            <select
              value={eventId}
              onChange={(e) => setEvent(+e.target.value)}
              className="max-w-72 rounded-md border bg-background px-2 py-1 text-sm"
              aria-label="Storm to replay"
            >
              {events.map((ev) => (
                <option key={ev.id} value={ev.id}>
                  {ev.name}
                  {ev.is_holdout ? " (test storm)" : ""}
                </option>
              ))}
              {!events.some((ev) => ev.id === eventId) && <option value={eventId}>Event {eventId}</option>}
            </select>
          </label>
        ) : (
          <p className="text-sm text-muted-foreground">
            Live warnings and storm news for South Florida from the National Weather Service and the National Hurricane Center. Our flood forecasts only run on past storms. Choose Storm replay to see them.
          </p>
        )}
      </CardContent>
    </Card>
  )
}
