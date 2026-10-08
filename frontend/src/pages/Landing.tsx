import { Link } from "react-router"
import { SpinningGlobe } from "@/components/spinning-globe"

// Starfield (CSS) behind a spinning night-lights Earth (three.js).
const STARS = Array.from({ length: 90 }, (_, i) => ({
  left: `${(i * 37.7) % 100}%`,
  top: `${(i * 53.3 + (i % 7) * 11) % 100}%`,
  size: 1 + (i % 3) * 0.6,
  opacity: 0.25 + ((i * 13) % 10) / 20,
}))

export default function Landing() {
  return (
    <main className="relative flex h-screen w-screen items-center justify-center overflow-hidden bg-[#02050c] text-white">
      {STARS.map((s, i) => (
        <span key={i} className="absolute rounded-full bg-white" style={{ left: s.left, top: s.top, width: s.size, height: s.size, opacity: s.opacity }} />
      ))}

      <SpinningGlobe className="absolute left-[27%] top-1/2 h-[120vh] w-[170vh] -translate-x-1/2 -translate-y-1/2" />

      <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-[#02050c]/70" />

      <div className="relative z-10 flex flex-col items-center text-center">
        <h1 className="bg-gradient-to-r from-white to-zinc-500 bg-clip-text text-6xl font-semibold tracking-[0.18em] text-transparent md:text-7xl"
          style={{ fontFamily: "Montserrat, 'Inter Variable', sans-serif" }}>
          SHROOMCAST
        </h1>
        <p className="mt-8 text-xs tracking-[0.55em] text-zinc-400 md:text-sm">CLEAR FORESIGHT FOR RISING WATERS.</p>
        <Link to="/dashboard" className="mt-12 rounded-full border border-white/25 px-8 py-2.5 text-xs tracking-[0.35em] text-white/80 transition hover:border-white/60 hover:bg-white/10 hover:text-white">
          ENTER DASHBOARD
        </Link>
      </div>

      <p className="absolute bottom-6 text-[10px] tracking-[0.25em] text-zinc-500">ZONE-LEVEL FLOOD INTELLIGENCE · DETERMINISTIC REPLAY</p>
    </main>
  )
}
