// Accuracy by forecast lead, built from the template's interactive area chart (chart-area-interactive):
// Card + header toggle (ToggleGroup on wide cards, Select on narrow) + gradient areas + dot tooltip.
// Differences from the template, on purpose: areas overlap instead of stacking (model and baseline are
// alternatives, not parts of a total), and the toggle switches the measure, never puts two scales on one axis.
import * as React from "react"
import { Area, AreaChart, CartesianGrid, ReferenceLine, XAxis, YAxis } from "recharts"

import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"

export interface LeadRow {
  lead: string
  errModel: number
  errPersistence: number
  covModel: number
  covPersistence?: number // recorded for leads 1 to 24 h only
}

type Measure = "error" | "coverage"
const MEASURES: Record<Measure, { label: string; sub: string; keys: [string, string] }> = {
  error: {
    label: "Water-level error",
    sub: "Mean absolute error in stage units, lower is better (units unverified: compare, don't read the number)",
    keys: ["errModel", "errPersistence"],
  },
  coverage: {
    label: "Range coverage",
    sub: "How often the truth falls inside the q10 to q90 range; the dashed line is the 80% target",
    keys: ["covModel", "covPersistence"],
  },
}

const chartConfig = {
  errModel: { label: "Our model", theme: { light: "#2a78d6", dark: "#3987e5" } },
  errPersistence: { label: "Persistence baseline", theme: { light: "#eb6834", dark: "#d95926" } },
  covModel: { label: "Our model", theme: { light: "#2a78d6", dark: "#3987e5" } },
  covPersistence: { label: "Persistence baseline", theme: { light: "#eb6834", dark: "#d95926" } },
} satisfies ChartConfig

export function ChartLeadInteractive({ data }: { data: LeadRow[] }) {
  const [measure, setMeasure] = React.useState<Measure>("error")
  const m = MEASURES[measure]
  const isPct = measure === "coverage"
  const fmt = (v: number) => (isPct ? `${Math.round(v * 100)}%` : v.toFixed(2))

  return (
    <Card className="@container/card">
      <CardHeader>
        <CardTitle>Accuracy by forecast lead</CardTitle>
        <CardDescription>
          <span className="hidden @[540px]/card:block">{m.sub}</span>
          <span className="@[540px]/card:hidden">{m.label}, 1 to 72 h ahead</span>
        </CardDescription>
        <CardAction>
          <ToggleGroup
            multiple={false}
            value={[measure]}
            onValueChange={(value) => setMeasure((value[0] as Measure) ?? "error")}
            variant="outline"
            className="hidden *:data-[slot=toggle-group-item]:px-4! @[767px]/card:flex"
          >
            <ToggleGroupItem value="error">Water-level error</ToggleGroupItem>
            <ToggleGroupItem value="coverage">Range coverage</ToggleGroupItem>
          </ToggleGroup>
          <Select value={measure} onValueChange={(value) => value !== null && setMeasure(value as Measure)}>
            <SelectTrigger
              className="flex w-44 **:data-[slot=select-value]:block **:data-[slot=select-value]:truncate @[767px]/card:hidden"
              size="sm"
              aria-label="Choose a measure"
            >
              <SelectValue placeholder="Water-level error" />
            </SelectTrigger>
            <SelectContent className="rounded-xl">
              <SelectItem value="error" className="rounded-lg">Water-level error</SelectItem>
              <SelectItem value="coverage" className="rounded-lg">Range coverage</SelectItem>
            </SelectContent>
          </Select>
        </CardAction>
      </CardHeader>
      <CardContent className="px-2 pt-4 sm:px-6 sm:pt-6">
        <ChartContainer config={chartConfig} className="aspect-auto h-[250px] w-full">
          <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <defs>
              {m.keys.map((k) => (
                <linearGradient key={k} id={`fill-${k}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={`var(--color-${k})`} stopOpacity={0.6} />
                  <stop offset="95%" stopColor={`var(--color-${k})`} stopOpacity={0.05} />
                </linearGradient>
              ))}
            </defs>
            <CartesianGrid vertical={false} />
            <XAxis dataKey="lead" tickLine={false} axisLine={false} tickMargin={8} />
            <YAxis
              tickLine={false} axisLine={false} width={44} tickFormatter={fmt}
              domain={isPct ? [0, 1] : [0, "auto"]} ticks={isPct ? [0, 0.2, 0.4, 0.6, 0.8, 1] : undefined}
            />
            {isPct && <ReferenceLine y={0.8} stroke="var(--muted-foreground)" strokeDasharray="4 4" />}
            <ChartTooltip
              cursor={false}
              content={
                <ChartTooltipContent
                  indicator="dot"
                  labelFormatter={(v) => `${v} ahead`}
                  formatter={(v, name) => `${chartConfig[name as keyof typeof chartConfig]?.label}: ${fmt(Number(v))}`}
                />
              }
            />
            <ChartLegend content={<ChartLegendContent />} />
            {m.keys.map((k) => (
              <Area
                key={k}
                dataKey={k}
                type="natural"
                fill={`url(#fill-${k})`}
                stroke={`var(--color-${k})`}
                strokeWidth={2}
                connectNulls={false}
              />
            ))}
          </AreaChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}
