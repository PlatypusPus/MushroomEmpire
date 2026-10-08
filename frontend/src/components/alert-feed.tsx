import * as React from "react"
import { toast } from "sonner"

import { clock, SEVERITY_COLOR, UNKNOWN_COLOR, type AlertEvent } from "@/api/client"
import { Badge } from "@/components/ui/badge"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { useReplayStore } from "@/state/replayStore"

const SHOWN = 12
const MAX_TOASTS_PER_TICK = 3 // a storm can fire dozens at once; toast the first few, the feed has the rest

export function AlertFeed({ feed, names, now }: { feed: AlertEvent[]; names: Map<string, string>; now: string | undefined }) {
  const { select, playing } = useReplayStore()
  const seen = React.useRef<Set<string>>(new Set())

  // toast alerts that fire on the tick being shown, only while playing (not when scrubbing back)
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

  const firedNow = feed.filter((a) => a.issue_ts === now).length
  return (
    <Card>
      <CardHeader>
        <CardTitle>Alerts</CardTitle>
        <CardDescription>A zone appears here when its probability crosses the validated alert threshold.</CardDescription>
        <CardAction>
          <Badge variant={firedNow ? "destructive" : "outline"}>{firedNow ? `${firedNow} new` : `${feed.length} fired`}</Badge>
        </CardAction>
      </CardHeader>
      <CardContent>
        {feed.length === 0 ? (
          <div className="text-sm text-muted-foreground">No alerts yet. Press play.</div>
        ) : (
          <ol className="flex max-h-72 flex-col gap-1 overflow-y-auto">
            {feed.slice(0, SHOWN).map((a) => (
              <li key={`${a.issue_ts}|${a.zone_id}`}>
                <button onClick={() => select(a.zone_id)} className="flex w-full gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted">
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
            {feed.length > SHOWN && <li className="px-2 text-xs text-muted-foreground">+{feed.length - SHOWN} earlier</li>}
          </ol>
        )}
      </CardContent>
    </Card>
  )
}
