// API & MCP: how other apps and AI assistants can get SHROOMCAST's data. Every example is live: "Try it" calls the same API.
import * as React from "react"
import { BotIcon, BracesIcon, CheckIcon, CopyIcon, ExternalLinkIcon, PlayIcon } from "lucide-react"

import { AppShell } from "@/components/app-shell"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

interface Endpoint { method: "GET" | "POST"; path: string; what: string; body?: object }

// Example ids that exist in the data: event 8 = 2023 Nov Extreme Rain Event, zone 1245000 = Miami, region 1 = South Florida
const GROUPS: { title: string; note: string; items: Endpoint[] }[] = [
  {
    title: "Storm replays (our flood forecast on past storms)",
    note: "Historical data. Each replay step is computed only from data available at that time.",
    items: [
      { method: "GET", path: "/events", what: "Storms you can replay, with dates." },
      { method: "POST", path: "/replay/8/start?step_h=3", what: "Start a replay; returns its time steps (use one as issue_ts)." },
      { method: "GET", path: "/ranking?event_id=8&issue_ts=2023-11-15T12:00:00Z", what: "Every place ranked for response at one time: chance, severity, timing, reasons." },
      { method: "GET", path: "/zones/1245000?event_id=8&issue_ts=2023-11-15T12:00:00Z", what: "One place in full: forecast, reasons, facilities, alert text." },
      { method: "GET", path: "/zones/1245000/mitigation?event_id=8&issue_ts=2023-11-15T12:00:00Z", what: "What to do there, who to call, nearest potential shelters." },
      { method: "GET", path: "/water?event_id=8&issue_ts=2023-11-15T12:00:00Z", what: "Where flood water may spread: affected neighbours and spill-zone shapes (GeoJSON)." },
      { method: "GET", path: "/regions/1/zones?event_id=8", what: "The 109 places with their outlines (GeoJSON), elevation and county." },
    ],
  },
  {
    title: "Live (now)",
    note: "Official warnings are from the National Weather Service and National Hurricane Center. Our live forecasts are experimental.",
    items: [
      { method: "GET", path: "/context", what: "Official alerts per county, active storms and the 0 to 4 hazard level." },
      { method: "GET", path: "/env", what: "Map layers: warning polygons, storm cone and track, radar frames, waves, air quality, wind." },
      { method: "GET", path: "/hazards/articles", what: "Full official texts: warnings, advisories, forecast discussions." },
      { method: "GET", path: "/mitigation/live/point?lat=30.5168&lon=-86.4822", what: "Any US point: official warnings there, steps, calls, nearest shelters." },
      { method: "GET", path: "/live/forecast?lat=25.86&lon=-80.30", what: "Our experimental 24 h forecast at the nearest USGS gauge." },
      { method: "GET", path: "/live/priority", what: "South Florida places ranked now (first call starts a few-minute run; poll until ready)." },
      { method: "GET", path: "/live/model", what: "Which model each region uses and what the last daily learning run did." },
    ],
  },
  {
    title: "Model quality and questions",
    note: "",
    items: [
      { method: "GET", path: "/models/1/metrics", what: "Validation results: hits, misses, false alarms, timing errors." },
      { method: "POST", path: "/assistant", what: "Ask in plain words; every number is checked against the data.", body: { question: "Which places should we prioritise first?", event_id: 8 } },
    ],
  },
]

const MCP_TOOLS: [string, string][] = [
  ["top_zones", "Places ranked for response at a replay time"],
  ["zone_detail", "Everything about one place at a replay time"],
  ["ask", "Ask the grounded assistant a question"],
  ["model_metrics", "Validation results for the model"],
  ["live_context", "Official alerts, storms and the hazard level now"],
  ["live_priority", "Places ranked now (experimental live forecast)"],
  ["live_forecast", "Our experimental forecast at the nearest gauge to a point"],
  ["advice_at", "What to do at any US point, with calls and shelters"],
]

function Copy({ text }: { text: string }) {
  const [done, setDone] = React.useState(false)
  return (
    <button type="button" aria-label="Copy" className="shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
      onClick={() => { navigator.clipboard?.writeText(text).then(() => { setDone(true); setTimeout(() => setDone(false), 1500) }).catch(() => {}) }}>
      {done ? <CheckIcon className="size-4 text-green-600" /> : <CopyIcon className="size-4" />}
    </button>
  )
}

function Code({ text }: { text: string }) {
  return (
    <div className="flex items-start gap-1 rounded-lg bg-muted/60 p-2">
      <pre className="min-w-0 flex-1 overflow-x-auto whitespace-pre font-mono text-xs leading-relaxed">{text}</pre>
      <Copy text={text} />
    </div>
  )
}

function EndpointRow({ e, base }: { e: Endpoint; base: string }) {
  const [out, setOut] = React.useState<string | null>(null)
  const [busy, setBusy] = React.useState(false)
  const url = `${base}${e.path}`
  const curl = e.body
    ? `curl -X POST "${url}" -H "Content-Type: application/json" -d '${JSON.stringify(e.body)}'`
    : e.method === "POST" ? `curl -X POST "${url}"` : `curl "${url}"`
  const run = async () => {
    setBusy(true)
    try {
      const r = await fetch(`/api${e.path}`, { method: e.method, headers: { "Content-Type": "application/json" }, body: e.body ? JSON.stringify(e.body) : undefined })
      const txt = JSON.stringify(await r.json(), null, 2)
      setOut(`HTTP ${r.status}\n${txt.length > 6000 ? `${txt.slice(0, 6000)}\n… (shortened, ${Math.round(txt.length / 1000)} kB in full)` : txt}`)
    } catch (err) {
      setOut(`Request failed: ${String(err)}`)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="flex flex-col gap-2 border-t py-4 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={e.method === "GET" ? "secondary" : "default"} className="font-mono">{e.method}</Badge>
        <code className="min-w-0 break-all font-mono text-sm font-semibold">/api{e.path}</code>
        <Button size="sm" variant="outline" className="ml-auto gap-1.5" onClick={run} disabled={busy}><PlayIcon className="size-3.5" />{busy ? "Running…" : "Try it"}</Button>
      </div>
      <p className="text-sm text-muted-foreground">{e.what}</p>
      <Code text={curl} />
      {out && <pre className="max-h-72 overflow-auto rounded-lg border bg-card p-2 font-mono text-[11px] leading-relaxed">{out}</pre>}
    </div>
  )
}

export default function ApiDocs() {
  const base = `${window.location.origin}/api`
  const claudeCode = "claude mcp add shroomcast -- uv run --directory /path/to/MushroomEmpire/backend python -m app.mcp_server"
  const desktop = JSON.stringify({ mcpServers: { shroomcast: { command: "uv", args: ["run", "--directory", "/path/to/MushroomEmpire/backend", "python", "-m", "app.mcp_server"] } } }, null, 2)
  return (
    <AppShell>
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-6 lg:px-6">
        <section className="rounded-2xl border bg-gradient-to-br from-sky-500/10 via-purple-500/10 to-emerald-500/10 p-6 md:p-8">
          <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground"><BracesIcon className="size-4" /> For developers</div>
          <h1 className="mt-2 text-3xl font-bold tracking-tight md:text-4xl">Use SHROOMCAST data</h1>
          <p className="mt-2 max-w-2xl text-base text-muted-foreground">
            Everything on the dashboard comes from a read-only JSON API, and AI assistants like Claude can use it through our MCP server.
            No key needed. Replays are past storms; live forecasts are experimental; we suggest, we never dispatch.
          </p>
          <div className="mt-4 flex flex-col gap-2">
            <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Base URL</span>
            <Code text={base} />
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button nativeButton={false} render={<a href="/docs" target="_blank" rel="noreferrer" />} className="gap-2">Interactive API docs <ExternalLinkIcon className="size-3.5" /></Button>
            <Button nativeButton={false} variant="outline" render={<a href="/openapi.json" target="_blank" rel="noreferrer" />}>OpenAPI spec (JSON)</Button>
            <Button nativeButton={false} variant="outline" render={<a href="#mcp" />} className="gap-2"><BotIcon className="size-4" /> MCP server</Button>
          </div>
        </section>

        {GROUPS.map((g) => (
          <Card key={g.title}>
            <CardHeader>
              <CardTitle>{g.title}</CardTitle>
              {g.note && <CardDescription>{g.note}</CardDescription>}
            </CardHeader>
            <CardContent>{g.items.map((e) => <EndpointRow key={e.method + e.path} e={e} base={base} />)}</CardContent>
          </Card>
        ))}
        <p className="-mt-2 text-xs text-muted-foreground">
          Account endpoints (followed places, alert history, WhatsApp) need a signed-in user and are listed in the interactive docs.
          Times are ISO 8601. Replay times use the stored gauge clock, which may be off by a few hours.
        </p>

        <Card id="mcp" className="scroll-mt-20">
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><BotIcon className="size-5" /> MCP server for AI assistants</CardTitle>
            <CardDescription>
              The Model Context Protocol lets assistants like Claude call SHROOMCAST directly and get the same answers as the dashboard.
              It runs on your machine from this repository (needs <code className="font-mono">uv</code>) and is read-only.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-5">
            <div className="flex flex-col gap-2">
              <span className="text-sm font-semibold">Claude Code</span>
              <Code text={claudeCode} />
            </div>
            <div className="flex flex-col gap-2">
              <span className="text-sm font-semibold">Claude Desktop (claude_desktop_config.json)</span>
              <Code text={desktop} />
            </div>
            <div className="flex flex-col gap-2">
              <span className="text-sm font-semibold">Run it on its own</span>
              <Code text="cd backend && uv run python -m app.mcp_server" />
            </div>
            <div>
              <span className="text-sm font-semibold">Tools</span>
              <ul className="mt-2 grid gap-2 sm:grid-cols-2">
                {MCP_TOOLS.map(([n, d]) => (
                  <li key={n} className="rounded-lg border px-3 py-2">
                    <code className="font-mono text-sm font-semibold">{n}</code>
                    <span className="block text-xs text-muted-foreground">{d}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <span className="text-sm font-semibold">Try asking</span>
              <ul className="mt-2 flex flex-col gap-1 text-sm text-muted-foreground">
                <li>"Which places should responders go to first in event 8 at 2023-11-15T12:00Z?"</li>
                <li>"What should people in Niceville, Florida do right now?"</li>
                <li>"How accurate is the flood model?"</li>
              </ul>
            </div>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  )
}
