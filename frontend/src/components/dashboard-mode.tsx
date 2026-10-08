// Dashboard mode: Live (official NWS and NHC hazards now) or Storm replay (the flood model on a past event, pick the event here).
// The flood model has no live gauge feed yet, so its forecasts exist only for replays. The live view says so instead of faking one.
import { RadioIcon, RewindIcon } from "lucide-react"

import type { CoastEvent } from "@/api/client"
import {
  NavigationMenu,
  NavigationMenuItem,
  NavigationMenuList,
  navigationMenuTriggerStyle,
} from "@/components/ui/navigation-menu"
import { cn } from "@/lib/utils"
import { useReplayStore } from "@/state/replayStore"

export function DashboardMode({ events }: { events: CoastEvent[] }) {
  const { mode, setMode, eventId, setEvent } = useReplayStore()
  return (
    <div className="flex shrink-0 flex-col gap-3 sm:flex-row sm:items-center">
      <NavigationMenu aria-label="Dashboard mode">
        <NavigationMenuList>
          <NavigationMenuItem>
            <button
              type="button"
              onClick={() => setMode("live")}
              aria-pressed={mode === "live"}
              data-active={mode === "live"}
              className={cn(navigationMenuTriggerStyle(), "cursor-pointer gap-1.5 data-[active=true]:bg-muted")}
            >
              <RadioIcon className="size-3.5" /> Live now
            </button>
          </NavigationMenuItem>
          <NavigationMenuItem>
            <button
              type="button"
              onClick={() => setMode("replay")}
              aria-pressed={mode === "replay"}
              data-active={mode === "replay"}
              className={cn(navigationMenuTriggerStyle(), "cursor-pointer gap-1.5 data-[active=true]:bg-muted")}
            >
              <RewindIcon className="size-3.5" /> Storm replay
            </button>
          </NavigationMenuItem>
        </NavigationMenuList>
      </NavigationMenu>
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
            </option>
          ))}
          {!events.some((ev) => ev.id === eventId) && <option value={eventId}>Event {eventId}</option>}
        </select>
      </label>
    </div>
  )
}
