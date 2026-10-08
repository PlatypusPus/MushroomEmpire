import "@fontsource-variable/montserrat"
import { useState } from "react"
import { useNavigate } from "react-router"
import { SpinningGlobe } from "@/components/spinning-globe"

// Starfield (CSS) behind a spinning night-lights Earth (three.js).
const STARS = Array.from({ length: 90 }, (_, i) => ({
  left: `${(i * 37.7) % 100}%`,
  top: `${(i * 53.3 + (i % 7) * 11) % 100}%`,
  size: 1 + (i % 3) * 0.6,
  opacity: 0.25 + ((i * 13) % 10) / 20,
}))

export default function Landing() {
  const nav = useNavigate()
  const [leaving, setLeaving] = useState(false)
  const enter = () => {
    if (leaving) return
    setLeaving(true)
    setTimeout(() => nav("/dashboard"), matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 900)
  }
  return (
    <main className={`relative flex h-screen w-screen items-center justify-center overflow-hidden bg-background text-white transition-opacity duration-[900ms] ease-in ${leaving ? "opacity-0" : "opacity-100"}`}>
      {STARS.map((s, i) => (
        <span key={i} className="absolute rounded-full bg-white" style={{ left: s.left, top: s.top, width: s.size, height: s.size, opacity: s.opacity }} />
      ))}

      <SpinningGlobe className={`absolute transition-transform duration-[900ms] ease-in ${leaving ? "scale-[1.6]" : "scale-100"} left-[72%] top-1/2 h-[120vh] w-[170vh] -translate-x-1/2 -translate-y-1/2`} />

      <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-background/70" />

      <div className="relative z-10 flex flex-col items-center text-center font-[Montserrat_Variable,'Inter_Variable',sans-serif]">
        <h1 className="bg-gradient-to-b from-white via-zinc-100 to-zinc-500 bg-clip-text text-6xl font-normal tracking-[0.2em] drop-shadow-[0_2px_24px_rgba(0,0,0,0.6)] text-transparent md:text-8xl">
          SHROOMCAST
        </h1>
        <div className="mt-7 h-px w-16 bg-white/30" />
        <p className="mt-7 text-[11px] font-medium tracking-[0.5em] text-zinc-300/80 md:text-sm">CLEAR FORESIGHT FOR RISING WATERS</p>
        <button type="button" onClick={enter} className="mt-14 rounded-full border border-white/30 bg-white/5 px-9 py-3 text-[11px] font-medium tracking-[0.35em] text-white/85 backdrop-blur-sm transition hover:border-white/70 hover:bg-white/15 hover:text-white">
          ENTER DASHBOARD
        </button>
      </div>
    </main>
  )
}
