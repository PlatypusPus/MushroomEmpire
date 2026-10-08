import type { Region, ZonePayload } from "@/api/client"
import { Card, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"

export function SectionCards({ payloads, region }: { payloads: ZonePayload[]; region: Region | undefined }) {
  const count = (f: (p: ZonePayload) => boolean) => payloads.filter(f).length
  const alerts = count((p) => p.is_alert)
  const unknown = count((p) => p.coverage === "insufficient_data")
  const facilities = payloads
    .filter((p) => p.is_alert)
    .reduce((n, p) => n + p.exposure.filter((a) => a.type === "hospital" || a.type === "shelter").length, 0)
  const cards = [
    { label: "Zones on alert", value: alerts, foot: `of ${payloads.length} Census places, validated alert threshold` },
    { label: "Hospitals and shelters in alerted zones", value: facilities, foot: "potentially exposed, from OSM" },
    { label: "Zones with insufficient data", value: unknown, foot: "unknown, never shown as low risk" },
    { label: "Coverage", value: region?.coverage ?? "...", foot: region?.name ?? "" },
  ]
  return (
    <div className="grid grid-cols-1 gap-4 px-4 lg:px-6 @xl/main:grid-cols-2 @5xl/main:grid-cols-4">
      {cards.map((c) => (
        <Card key={c.label} className="@container/card">
          <CardHeader>
            <CardDescription>{c.label}</CardDescription>
            <CardTitle className="text-2xl font-semibold capitalize tabular-nums">{c.value}</CardTitle>
          </CardHeader>
          <CardFooter className="text-xs text-muted-foreground">{c.foot}</CardFooter>
        </Card>
      ))}
    </div>
  )
}
