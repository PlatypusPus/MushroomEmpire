// First-visit guided tour of the dashboard. Each step spotlights an element marked data-tour="<key>" and shows a short caption.
// Opens by itself once per browser (localStorage), and again from the Tutorials page or the sidebar.
import * as React from "react"
import { XIcon } from "lucide-react"
import { create } from "zustand"

import { Button } from "@/components/ui/button"
import { useReplayStore } from "@/state/replayStore"

const SEEN_KEY = "shroomcast.tour.seen"

interface Step {
  target?: string // data-tour key; none = centred card
  title: string
  body: string
  mode?: "live" | "replay" // switch the dashboard first, so the highlighted part exists
}

export const STEPS: Step[] = [
  { title: "Welcome to SHROOMCAST", body: "See where South Florida may flood, why, and what to do. This tour takes about a minute." },
  { target: "mode", mode: "replay", title: "Two modes", body: "Storm replay runs our flood forecast on a past storm. Live now shows today's official warnings." },
  { target: "map", mode: "replay", title: "The map", body: "Each place is coloured by its flood risk. Click a place to open its details." },
  { target: "legend", mode: "replay", title: "Colours", body: "Green is low, red is severe. Grey means we do not know, which never means safe." },
  { target: "player", mode: "replay", title: "Play the storm", body: "Press play to watch the storm unfold, or drag to any moment." },
  { target: "panel", mode: "replay", title: "Place details", body: "Chance, how bad, when it starts, why, and a What to do tab. Chat lets you ask about it." },
  { target: "map", mode: "live", title: "Live now", body: "Click anywhere, even outside South Florida, for the official warnings there and what to do." },
  { target: "nav-priority", title: "Response priority", body: "Places ranked for emergency teams. Sliders change what matters most." },
  { target: "nav-alerts", title: "Alerts", body: "Every place that crossed the alert line. Sign in to get alerts by email or WhatsApp." },
  { target: "nav-assistant", title: "Assistant", body: "Ask in plain words, like: Why is Miami at risk?" },
  { target: "nav-tutorials", title: "Need help later?", body: "Tutorials explain every page, and can replay this tour." },
]

export const useTour = create<{ step: number | null; start: () => void; stop: () => void; go: (i: number) => void }>((set) => ({
  step: null,
  start: () => set({ step: 0 }),
  stop: () => {
    try { localStorage.setItem(SEEN_KEY, "1") } catch { /* private mode: the tour may show again next visit */ }
    if (useReplayStore.getState().mode === "live") useReplayStore.getState().setMode("replay") // back to the default view
    set({ step: null })
  },
  go: (step) => set({ step }),
}))

/** Start the tour on the first dashboard visit in this browser. */
export function useFirstVisitTour() {
  React.useEffect(() => {
    let seen = false
    try { seen = localStorage.getItem(SEEN_KEY) === "1" } catch { seen = true } // storage blocked: do not nag every load
    if (!seen) {
      const t = setTimeout(() => useTour.getState().start(), 800) // let the map lay out first
      return () => clearTimeout(t)
    }
  }, [])
}

function useRect(target: string | undefined, step: number) {
  const [rect, setRect] = React.useState<DOMRect | null>(null)
  React.useEffect(() => {
    if (!target) return setRect(null)
    let raf = 0
    const measure = () => {
      const el = Array.from(document.querySelectorAll<HTMLElement>(`[data-tour="${target}"]`)).find((e) => e.offsetParent !== null)
      setRect(el ? el.getBoundingClientRect() : null)
    }
    const el = document.querySelector<HTMLElement>(`[data-tour="${target}"]`)
    el?.scrollIntoView({ block: "nearest", behavior: "smooth" })
    const t = setTimeout(measure, 350) // after a mode switch re-renders and the scroll settles
    const onChange = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(measure) }
    window.addEventListener("resize", onChange)
    window.addEventListener("scroll", onChange, true)
    return () => {
      clearTimeout(t)
      cancelAnimationFrame(raf)
      window.removeEventListener("resize", onChange)
      window.removeEventListener("scroll", onChange, true)
    }
  }, [target, step])
  return rect
}

export function Tour() {
  const { step, stop, go } = useTour()
  const s = step == null ? undefined : STEPS[step]
  const rect = useRect(s?.target, step ?? -1)

  React.useEffect(() => {
    if (s?.mode && useReplayStore.getState().mode !== s.mode) useReplayStore.getState().setMode(s.mode)
  }, [s])
  React.useEffect(() => {
    if (step == null) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") stop()
      if (e.key === "ArrowRight") go(Math.min(step + 1, STEPS.length - 1))
      if (e.key === "ArrowLeft") go(Math.max(step - 1, 0))
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [step, stop, go])

  if (step == null || !s) return null
  const last = step === STEPS.length - 1
  const pad = 6
  // caption below the spotlight when it sits in the top half, else above; centred when there is no target
  const W = Math.min(340, window.innerWidth - 32)
  const beside = rect && rect.right + W + 32 < window.innerWidth && rect.width < 400 && rect.left < 120 // sidebar items: caption to the right
  const card: React.CSSProperties = beside
    ? { left: rect.right + pad + 12, top: Math.min(Math.max(16, rect.top - 24), window.innerHeight - 220), width: W }
    : rect
    ? {
        left: Math.min(Math.max(16, rect.left + rect.width / 2 - W / 2), window.innerWidth - W - 16),
        ...(rect.top + rect.height / 2 < window.innerHeight / 2
          ? { top: Math.min(rect.bottom + pad + 12, window.innerHeight - 220) }
          : { bottom: Math.min(window.innerHeight - rect.top + pad + 12, window.innerHeight - 220) }),
        width: W,
      }
    : { left: "50%", top: "50%", transform: "translate(-50%, -50%)", width: W }

  return (
    <div className="fixed inset-0 z-[2000]" role="dialog" aria-modal="true" aria-labelledby="tour-title">
      {rect ? (
        <div
          className="pointer-events-none absolute rounded-xl ring-2 ring-primary transition-all duration-300"
          style={{ left: rect.left - pad, top: rect.top - pad, width: rect.width + pad * 2, height: rect.height + pad * 2, boxShadow: "0 0 0 9999px rgb(0 0 0 / 0.6)" }}
        />
      ) : (
        <div className="absolute inset-0 bg-black/60" />
      )}
      <div className="absolute flex flex-col gap-3 rounded-xl border bg-card p-4 shadow-2xl transition-all duration-300 animate-in fade-in zoom-in-95" style={card}>
        <div className="flex items-start gap-2">
          <h2 id="tour-title" className="flex-1 text-lg font-bold tracking-tight">{s.title}</h2>
          <button onClick={stop} aria-label="Close tour" className="rounded-md p-1 text-muted-foreground hover:bg-muted"><XIcon className="size-4" /></button>
        </div>
        <p className="text-sm leading-relaxed">{s.body}</p>
        {!rect && s.target?.startsWith("nav-") && <p className="text-xs text-muted-foreground">Open it from the menu button at the top left.</p>}
        <div className="flex items-center gap-2">
          <div className="flex flex-1 gap-1" aria-label={`Step ${step + 1} of ${STEPS.length}`}>
            {STEPS.map((_, i) => (
              <span key={i} className={`h-1.5 rounded-full transition-all ${i === step ? "w-4 bg-primary" : "w-1.5 bg-muted-foreground/30"}`} />
            ))}
          </div>
          {step > 0 && <Button variant="ghost" size="sm" onClick={() => go(step - 1)}>Back</Button>}
          <Button size="sm" onClick={() => (last ? stop() : go(step + 1))} autoFocus>{last ? "Done" : step === 0 ? "Start" : "Next"}</Button>
        </div>
        {step === 0 && <button onClick={stop} className="self-start text-xs text-muted-foreground underline underline-offset-2">Skip the tour</button>}
      </div>
    </div>
  )
}
