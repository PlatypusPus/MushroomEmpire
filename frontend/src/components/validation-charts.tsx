// Charts for the Model validation page, built on the shadcn chart components (components/ui/chart.tsx).
// Colours: our model blue vs persistence baseline orange (dataviz palette, colour-blind separation validated in
// light and dark); status colours only for caught / false alarm / missed, always with a legend label.
import { Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, Scatter, ScatterChart, XAxis, YAxis, ZAxis } from "recharts"

import {
  type ChartConfig,
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart"

const MODEL = { light: "#2a78d6", dark: "#3987e5" }
const BASE = { light: "#eb6834", dark: "#d95926" }
const BOX = "aspect-auto h-[240px] w-full"
const pct = (v: number) => `${Math.round(v * 100)}%`

const vsConfig = {
  model: { label: "Our model", theme: MODEL },
  persistence: { label: "Persistence baseline", theme: BASE },
} satisfies ChartConfig

/** Water-level error by lead: model vs persistence. Lower is better. */
export function ErrorByLeadChart({ data }: { data: { lead: string; model: number; persistence: number }[] }) {
  return (
    <ChartContainer config={vsConfig} className={BOX}>
      <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="lead" tickLine={false} axisLine={false} />
        <YAxis tickLine={false} axisLine={false} width={36} tickFormatter={(v) => v.toFixed(1)} />
        <ChartTooltip content={<ChartTooltipContent formatter={(v, name) => `${vsConfig[name as keyof typeof vsConfig]?.label}: ${Number(v).toFixed(2)}`} />} />
        <ChartLegend content={<ChartLegendContent />} />
        {(["model", "persistence"] as const).map((k) => (
          <Line key={k} dataKey={k} stroke={`var(--color-${k})`} strokeWidth={2}
            dot={{ r: 4, fill: `var(--color-${k})`, stroke: "var(--card)", strokeWidth: 2 }} />
        ))}
      </LineChart>
    </ChartContainer>
  )
}

/** PR-AUC, model vs persistence, per question. Higher is better. */
export function SkillChart({ data }: { data: { measure: string; model: number; persistence: number }[] }) {
  return (
    <ChartContainer config={vsConfig} className={BOX}>
      <BarChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }} barGap={2}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="measure" tickLine={false} axisLine={false} />
        <YAxis domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tickLine={false} axisLine={false} width={40} tickFormatter={(v) => v.toFixed(2)} />
        <ChartTooltip content={<ChartTooltipContent formatter={(v, name) => `${vsConfig[name as keyof typeof vsConfig]?.label}: ${Number(v).toFixed(2)}`} />} />
        <ChartLegend content={<ChartLegendContent />} />
        <Bar dataKey="model" fill="var(--color-model)" radius={[4, 4, 0, 0]} />
        <Bar dataKey="persistence" fill="var(--color-persistence)" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ChartContainer>
  )
}

const calConfig = { observed: { label: "Observed rate", theme: MODEL } } satisfies ChartConfig

/** Predicted vs observed rate per probability band; the dashed diagonal is perfect calibration. */
export function CalibrationChart({ data }: { data: { predicted: number; observed: number; n: number; bin: string }[] }) {
  return (
    <ChartContainer config={calConfig} className={BOX}>
      <ScatterChart margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid />
        <XAxis type="number" dataKey="predicted" domain={[0, 1]} tickLine={false} axisLine={false} tickFormatter={pct} />
        <YAxis type="number" dataKey="observed" domain={[0, 1]} tickLine={false} axisLine={false} width={40} tickFormatter={pct} />
        <ZAxis dataKey="n" range={[60, 60]} />
        <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke="var(--muted-foreground)" strokeDasharray="4 4" />
        <ChartTooltip
          cursor={{ strokeDasharray: "3 3" }}
          content={
            <ChartTooltipContent
              hideLabel
              formatter={(_, __, item) => {
                const d = item.payload as { bin: string; predicted: number; observed: number; n: number }
                return `Band ${d.bin}: predicted ${pct(d.predicted)}, observed ${pct(d.observed)} (${d.n.toLocaleString()} cases)`
              }}
            />
          }
        />
        <Scatter dataKey="observed" data={data} fill="var(--color-observed)" stroke="var(--card)" strokeWidth={2}
          line={{ stroke: "var(--color-observed)", strokeWidth: 2 }} />
      </ScatterChart>
    </ChartContainer>
  )
}

const detConfig = {
  caught: { label: "Caught", color: "#0ca30c" },
  falseAlarms: { label: "False alarms", color: "#fab219" },
  missed: { label: "Missed", color: "#d03b3b" },
} satisfies ChartConfig

/** Caught / false alarms / missed per case, stacked horizontally. */
export function DetectionChart({ data }: { data: { case: string; caught: number; falseAlarms: number; missed: number }[] }) {
  return (
    <ChartContainer config={detConfig} className={BOX}>
      <BarChart data={data} layout="vertical" margin={{ top: 8, right: 16, left: 8, bottom: 0 }} barCategoryGap={18}>
        <CartesianGrid horizontal={false} />
        <XAxis type="number" tickLine={false} axisLine={false} tickFormatter={(v) => v.toLocaleString()} />
        <YAxis type="category" dataKey="case" tickLine={false} axisLine={false} width={120} />
        <ChartTooltip content={<ChartTooltipContent />} />
        <ChartLegend content={<ChartLegendContent />} />
        <Bar dataKey="caught" stackId="a" fill="var(--color-caught)" stroke="var(--card)" strokeWidth={2} />
        <Bar dataKey="falseAlarms" stackId="a" fill="var(--color-falseAlarms)" stroke="var(--card)" strokeWidth={2} />
        <Bar dataKey="missed" stackId="a" fill="var(--color-missed)" stroke="var(--card)" strokeWidth={2} radius={[0, 4, 4, 0]} />
      </BarChart>
    </ChartContainer>
  )
}

/** One series: peak error per method (hours) or recall per onset-lead band (share). */
export function SimpleBarChart({ data, unit, label }: { data: { label: string; value: number }[]; unit: "h" | "%"; label: string }) {
  const fmt = (v: number) => (unit === "%" ? pct(v) : `${v.toFixed(1)} h`)
  const config = { value: { label, theme: MODEL } } satisfies ChartConfig
  return (
    <ChartContainer config={config} className={BOX}>
      <BarChart data={data} margin={{ top: 24, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="label" tickLine={false} axisLine={false} interval={0} />
        <YAxis domain={unit === "%" ? [0, 1] : [0, "auto"]} tickLine={false} axisLine={false} width={40} tickFormatter={fmt} />
        <ChartTooltip content={<ChartTooltipContent formatter={(v) => `${label}: ${fmt(Number(v))}`} />} />
        <Bar dataKey="value" fill="var(--color-value)" radius={[4, 4, 0, 0]}
          label={{ position: "top", fontSize: 12, fill: "var(--foreground)", formatter: (v) => (typeof v === "number" ? fmt(v) : "") }} />
      </BarChart>
    </ChartContainer>
  )
}
