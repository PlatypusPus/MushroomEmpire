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
    { label: "Places on alert", value: `${alerts}/${payloads.length}` },
    { label: "Hospitals and shelters in alert places", value: facilities, foot: "could be hit, from OpenStreetMap" },
    { label: "Places with not enough data", value: unknown, foot: "risk unknown, never shown as low" },
    { label: "How well tested", value: region?.coverage ?? "...", foot: region?.name ?? "" },
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
