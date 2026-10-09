import { SEVERITY_COLOR, UNKNOWN_COLOR, type Weights, type ZonePayload } from "@/api/client"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { DEFAULT_WEIGHTS, useReplayStore } from "@/state/replayStore"

const LABELS: Record<keyof Weights, string> = {
  probability: "Chance of flooding",
  severity: "How bad",
  urgency: "How soon",
  exposure: "Facilities at risk",
  vulnerable: "Hospitals and shelters",
  uncertainty: "Timing doubt",
}
// What each factor measures (0 to 1) and what raising its weight does. Mirrors backend/app/agents/ranking.py terms().
const HELP: Record<keyof Weights, string> = {
  probability: "The model's chance this place floods. Raise it to put the likeliest places first.",
  severity: "Expected depth: low 0, moderate 0.33, high 0.67, severe 1. Raise it to put the worst floods first.",
  urgency: "How close the start is: now 1, in 6 h 0.5, in 18 h 0.25. Raise it to put the earliest floods first.",
  exposure: "Mapped roads, buildings and facilities, compared with the busiest place. Raise it to protect the most.",
  vulnerable: "Hospitals and potential shelters only. These are also in Facilities, so this gives them extra weight.",
  uncertainty: "How wide the start-time window is. Raise it to go early where timing is least sure. Off by default.",
}
const SHOWN = 10

export function RankingQueue({ payloads, names }: { payloads: ZonePayload[]; names: Map<string, string> }) {
  const { weights, setWeight, selectedZone, select } = useReplayStore()
  return (
    <Card>
      <CardHeader>
        <CardTitle>Response priority</CardTitle>
        <CardDescription>
          Score = each factor (0 to 1) times its weight, added up. Only how big the weights are compared with each other matters; 0 ignores a factor.
          It suggests an order and never sends anyone.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-col gap-3">
          {(Object.keys(LABELS) as (keyof Weights)[]).map((k) => (
            <div key={k}>
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-sm font-medium">{LABELS[k]}</span>
                <span className="text-xs font-semibold tabular-nums">{weights[k].toFixed(2)}</span>
              </div>
              <input
                type="range" min={0} max={1} step={0.05} value={weights[k]} aria-label={LABELS[k]}
                onChange={(e) => setWeight(k, +e.target.value)} className="w-full accent-primary"
              />
              <p className="text-[11px] leading-snug text-muted-foreground">{HELP[k]}</p>
            </div>
          ))}
          <Button variant="outline" size="sm" className="self-start" onClick={() => useReplayStore.setState({ weights: DEFAULT_WEIGHTS })}>
            Reset to defaults
          </Button>
        </div>
        <p className="text-[11px] text-muted-foreground">Next to each place: the two factors adding the most to its score.</p>
        <ol className="flex flex-col gap-1">
          {payloads.slice(0, SHOWN).map((p) => (
            <li key={p.zone_id}>
              <button
                onClick={() => select(p.zone_id)}
                className={`flex w-full items-center gap-3 rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted ${
                  selectedZone === p.zone_id ? "bg-muted" : ""
                }`}
              >
                <span className="w-6 text-muted-foreground tabular-nums">{p.rank}</span>
                <span
                  className="inline-block size-2.5 shrink-0 rounded-full"
                  style={{ backgroundColor: p.severity ? SEVERITY_COLOR[p.severity] : UNKNOWN_COLOR }}
                />
                <span className="flex min-w-0 flex-1 flex-col sm:flex-row sm:items-center sm:gap-3">
                  <span className="truncate font-medium">{names.get(p.zone_id) ?? p.zone_id}</span>
                  <span className="truncate text-xs text-muted-foreground sm:ml-auto">{p.rank_reason}</span>
                </span>
              </button>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  )
}
