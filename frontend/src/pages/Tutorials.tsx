// Tutorials: short how-tos for every page, how to read the colours and levels, common questions, and a button to replay the tour.
import type { ReactNode } from "react"
import { Link, useNavigate } from "react-router"
import {
  BellRingIcon, ChartColumnIcon, ChevronDownIcon, ListOrderedIcon, MapPinnedIcon, MessageSquareIcon, MousePointerClickIcon,
  PlayIcon, RadioIcon, RewindIcon, SparklesIcon,
} from "lucide-react"

import { SEVERITY_COLOR, UNKNOWN_COLOR, type Severity } from "@/api/client"
import { AppShell } from "@/components/app-shell"
import { officialStatus } from "@/components/live-hazard"
import { useTour } from "@/components/tour"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useReplayStore } from "@/state/replayStore"

interface Guide { icon: ReactNode; title: string; steps: string[]; to: string; open: string; mode?: "live" | "replay" }

const GUIDES: Guide[] = [
  { icon: <RewindIcon className="size-5 text-orange-500" />, title: "Replay a past storm", to: "/dashboard", open: "Open the dashboard", mode: "replay",
    steps: ["Choose Storm replay and pick an event.", "Press play, or drag the timeline.", "Watch places change colour as risk rises."] },
  { icon: <RadioIcon className="size-5 text-red-500" />, title: "Check live warnings", to: "/dashboard", open: "Open Live now", mode: "live",
    steps: ["Choose Live now.", "Click anywhere on the map, even outside South Florida.", "Read the official status and the steps to take."] },
  { icon: <MousePointerClickIcon className="size-5 text-sky-500" />, title: "Read a place", to: "/dashboard", open: "Try it",  mode: "replay",
    steps: ["Click a place on the map.", "See chance, how bad, and when it starts.", "Open Why for the reasons, What to do for steps, calls and shelters."] },
  { icon: <ListOrderedIcon className="size-5 text-purple-500" />, title: "Plan a response", to: "/priority", open: "Open Response priority",
    steps: ["Places are ranked for emergency teams.", "Move the sliders to change what matters most.", "Click a place in the list to see it on the map."] },
  { icon: <BellRingIcon className="size-5 text-yellow-500" />, title: "Get alerts", to: "/account", open: "Sign in",
    steps: ["Sign in with Google.", "Pick the places you care about.", "Get alerts by email, and by WhatsApp after a quick code check."] },
  { icon: <MessageSquareIcon className="size-5 text-green-500" />, title: "Ask the assistant", to: "/chat", open: "Open the assistant",
    steps: ["Ask in plain words: Why is Miami at risk?", "It answers from the same data as the map.", "Every number is checked before you see it."] },
  { icon: <ChartColumnIcon className="size-5 text-muted-foreground" />, title: "Check how good it is", to: "/validation", open: "Open Model validation",
    steps: ["See how the forecast did on storms it never trained on.", "Hit rates, false alarms and timing errors, with no spin."] },
]

const FAQ: [string, string][] = [
  ["Is grey safe?", "No. Grey means there is no working water sensor nearby, so the risk is unknown."],
  ["Is the replay happening now?", "No. Storm replay is a past storm, labelled as practice. Live now is today."],
  ["Why is my town not coloured?", "The flood forecast covers Miami-Dade and Broward. In Live now you can still click anywhere for official warnings."],
  ["Does SHROOMCAST send rescuers?", "No. It only suggests an order. People decide and act."],
  ["Is that shelter open?", "Maybe not. Shelters listed are schools and community centres. Call your county line first."],
  ["Where does live data come from?", "The National Weather Service and the National Hurricane Center. It never feeds our forecast."],
  ["Does the forecast keep learning?", "Yes. Every day it trains on new readings from US water gauges, and only switches to the new version if it does better on the latest two weeks. Outside South Florida it is marked experimental."],
]

export default function Tutorials() {
  const navigate = useNavigate()
  const tour = () => {
    useTour.getState().start()
    navigate("/dashboard")
  }
  const open = (g: Guide) => {
    if (g.mode) useReplayStore.getState().setMode(g.mode)
    navigate(g.to)
  }

  return (
    <AppShell>
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-6 lg:px-6">
        <section className="relative overflow-hidden rounded-2xl border bg-gradient-to-br from-sky-500/15 via-purple-500/10 to-orange-500/15 p-6 md:p-8">
          <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground"><SparklesIcon className="size-4" /> Tutorials</div>
          <h1 className="mt-2 text-3xl font-bold tracking-tight md:text-4xl">Learn SHROOMCAST in 2 minutes</h1>
          <p className="mt-2 max-w-xl text-base text-muted-foreground">See where South Florida may flood, why, and what to do.</p>
          <div className="mt-5 flex flex-wrap gap-2">
            <Button size="lg" onClick={tour} className="gap-2"><PlayIcon className="size-4" /> Take the 1-minute tour</Button>
            <Button size="lg" variant="outline" nativeButton={false} render={<Link to="/dashboard" />}>Go to the dashboard</Button>
          </div>
        </section>

        <section>
          <h2 className="mb-3 text-xl font-bold tracking-tight">Start here</h2>
          <ol className="grid gap-3 sm:grid-cols-3">
            {[["Pick a mode", "Storm replay or Live now."], ["Click a place", "On the map."], ["Follow What to do", "Steps, calls, shelters."]].map(([t, d], i) => (
              <li key={t} className="flex items-center gap-3 rounded-xl border p-4">
                <span className="grid size-9 shrink-0 place-items-center rounded-full bg-primary text-base font-bold text-primary-foreground">{i + 1}</span>
                <div><div className="font-semibold">{t}</div><div className="text-sm text-muted-foreground">{d}</div></div>
              </li>
            ))}
          </ol>
        </section>

        <section>
          <h2 className="mb-3 text-xl font-bold tracking-tight">How to…</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {GUIDES.map((g) => (
              <Card key={g.title} className="transition-colors hover:border-primary/50">
                <CardHeader><CardTitle className="flex items-center gap-2 text-base">{g.icon}{g.title}</CardTitle></CardHeader>
                <CardContent className="flex flex-1 flex-col gap-3">
                  <ol className="flex flex-col gap-1.5 text-sm">
                    {g.steps.map((s, i) => (
                      <li key={s} className="flex gap-2"><span className="font-bold text-muted-foreground tabular-nums">{i + 1}.</span>{s}</li>
                    ))}
                  </ol>
                  <Button variant="outline" size="sm" className="mt-auto self-start" onClick={() => open(g)}>{g.open}</Button>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>

        <section className="grid gap-3 md:grid-cols-2">
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2 text-base"><MapPinnedIcon className="size-5" /> Flood risk colours (replay)</CardTitle></CardHeader>
            <CardContent className="flex flex-col gap-2 text-sm">
              {(Object.keys(SEVERITY_COLOR) as Severity[]).map((s) => (
                <div key={s} className="flex items-center gap-2.5"><span className="size-4 rounded" style={{ background: SEVERITY_COLOR[s] }} /><span className="font-medium capitalize">{s}</span></div>
              ))}
              <div className="flex items-center gap-2.5"><span className="size-4 rounded" style={{ background: UNKNOWN_COLOR }} /><span className="font-medium">Unknown, never safe</span></div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2 text-base"><RadioIcon className="size-5" /> Official levels (live)</CardTitle></CardHeader>
            <CardContent className="flex flex-col gap-2 text-sm">
              {[0, 1, 2, 3, 4].map((l) => {
                const st = officialStatus(l)
                const what = ["Nothing issued", "Minor flooding possible", "Flooding possible, be ready", "Flooding now or very soon", "Hurricane or storm surge warning"][l]
                return (
                  <div key={l} className="flex items-center gap-2.5">
                    <span className="w-36 shrink-0 whitespace-nowrap rounded-full px-2.5 py-0.5 text-center text-xs font-bold uppercase" style={{ background: st.color, color: st.ink }}>{st.word}</span>
                    <span className="text-muted-foreground">{what}</span>
                  </div>
                )
              })}
            </CardContent>
          </Card>
        </section>

        <section>
          <h2 className="mb-3 text-xl font-bold tracking-tight">Common questions</h2>
          <div className="flex flex-col divide-y rounded-xl border">
            {FAQ.map(([q, a]) => (
              <details key={q} className="group px-4 py-3">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-2 font-medium">
                  {q}<ChevronDownIcon className="size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
                </summary>
                <p className="mt-2 text-sm text-muted-foreground">{a}</p>
              </details>
            ))}
          </div>
        </section>
      </div>
    </AppShell>
  )
}
