import * as React from "react"
import { toast } from "sonner"

import { clock, SEVERITY_COLOR, UNKNOWN_COLOR, type AlertEvent } from "@/api/client"
import { Badge } from "@/components/ui/badge"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { useReplayStore } from "@/state/replayStore"

const MAX_TOASTS_PER_TICK = 3 // a storm can fire dozens at once; toast the first few, the alerts page has the rest

/** Pop-up toasts for alerts that fire on the tick being shown, only while the replay plays (not when scrubbing). */
export function useAlertToasts(feed: AlertEvent[], names: Map<string, string>, now: string | undefined) {
  const { select, playing } = useReplayStore()
  const seen = React.useRef<Set<string>>(new Set())
  React.useEffect(() => {
    const key = (a: AlertEvent) => `${a.issue_ts}|${a.zone_id}`
    const fresh = feed.filter((a) => a.issue_ts === now && !seen.current.has(key(a)))
    feed.forEach((a) => seen.current.add(key(a)))
    if (!playing) return
    fresh.slice(0, MAX_TOASTS_PER_TICK).forEach((a) =>
      toast.warning(names.get(a.zone_id) ?? a.zone_id, {
        description: a.alert_text,
        action: { label: "View", onClick: () => select(a.zone_id) },
      })
    )
    if (fresh.length > MAX_TOASTS_PER_TICK) toast(`+${fresh.length - MAX_TOASTS_PER_TICK} more alerts at ${clock(now!)}`)
  }, [feed, now, playing, names, select])
}

export function AlertFeed({ feed, names, now, onPick }: {
  feed: AlertEvent[]
  names: Map<string, string>
  now: string | undefined
  onPick: (zoneId: string) => void
}) {
  const firedNow = feed.filter((a) => a.issue_ts === now).length
  return (
    <Card>
      <CardHeader>
        <CardTitle>Alert feed</CardTitle>
        <CardDescription>
          A place shows up here when its flood chance passes the alert line, and shows up again only after 24 hours below the line.
          Up to the time shown{now ? ` (${clock(now, true)})` : ""}, newest first.
        </CardDescription>
        <CardAction>
          <Badge variant={firedNow ? "destructive" : "outline"}>{firedNow ? `${firedNow} new` : `${feed.length} fired`}</Badge>
        </CardAction>
      </CardHeader>
      <CardContent>
        {feed.length === 0 ? (
          <div className="text-sm text-muted-foreground">No alerts yet. Press play on the dashboard.</div>
        ) : (
          <ol className="flex flex-col gap-1">
            {feed.map((a) => (
              <li key={`${a.issue_ts}|${a.zone_id}`}>
                <button onClick={() => onPick(a.zone_id)} className="flex w-full gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted">
                  <span
                    className="mt-1.5 inline-block size-2.5 shrink-0 rounded-full"
                    style={{ backgroundColor: a.severity ? SEVERITY_COLOR[a.severity] : UNKNOWN_COLOR }}
                  />
                  <span className="flex-1">
                    <span className="font-medium">{names.get(a.zone_id) ?? a.zone_id}</span>
                    <span className="ml-2 text-xs text-muted-foreground tabular-nums">
                      {clock(a.issue_ts, true)} · {Math.round((a.probability ?? 0) * 100)}%
                    </span>
                    {a.issue_ts === now && <Badge variant="destructive" className="ml-2">new</Badge>}
                    <span className="block text-xs text-muted-foreground">{a.alert_text}</span>
                  </span>
                </button>
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  )
}
