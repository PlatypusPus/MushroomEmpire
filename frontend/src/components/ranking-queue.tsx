import { SEVERITY_COLOR, UNKNOWN_COLOR, type Weights, type ZonePayload } from "@/api/client"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { useReplayStore } from "@/state/replayStore"

const LABELS: Record<keyof Weights, string> = {
  probability: "Chance of flooding",
  severity: "How bad",
  urgency: "How soon",
  exposure: "Facilities at risk",
  vulnerable: "Hospitals and shelters",
  uncertainty: "Timing doubt",
}
const SHOWN = 10

export function RankingQueue({ payloads, names }: { payloads: ZonePayload[]; names: Map<string, string> }) {
  const { weights, setWeight, selectedZone, select } = useReplayStore()
  return (
    <Card>
      <CardHeader>
        <CardTitle>Response priority</CardTitle>
        <CardDescription>A simple score you can adjust. It suggests an order and never sends anyone.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2">
          {(Object.keys(LABELS) as (keyof Weights)[]).map((k) => (
            <label key={k} className="flex items-center gap-2 text-xs">
              <span className="w-36 shrink-0 text-muted-foreground">{LABELS[k]}</span>
              <input
                type="range" min={0} max={1} step={0.05} value={weights[k]}
                onChange={(e) => setWeight(k, +e.target.value)} className="flex-1 accent-primary"
              />
              <span className="w-8 tabular-nums">{weights[k].toFixed(2)}</span>
            </label>
          ))}
        </div>
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
                <span className="flex-1 truncate font-medium">{names.get(p.zone_id) ?? p.zone_id}</span>
                <span className="hidden truncate text-xs text-muted-foreground sm:block">{p.rank_reason}</span>
              </button>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  )
}
