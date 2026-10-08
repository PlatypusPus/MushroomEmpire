import { Link } from "react-router"

// Pure CSS scene (no image asset): starfield, lens-flare sun, night-side Earth with a lit limb and city lights.
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

      {/* sun */}
      <div className="absolute left-[20%] top-[32%] size-[300px] -translate-x-1/2 -translate-y-1/2"
        style={{ background: "radial-gradient(circle, #fff 0 4%, #cfe6ff 8%, rgba(70,140,255,.45) 18%, rgba(30,80,200,.18) 38%, transparent 66%)" }} />

      {/* earth */}
      <div className="absolute left-[34%] top-1/2 aspect-square h-[130vh] -translate-y-1/2 rounded-full"
        style={{
          background:
            "radial-gradient(circle at 75% 45%, #0a1426 0, #050a14 40%, #02050b 75%)",
          boxShadow:
            "inset 14px 0 18px -6px #cfe6ff, inset 60px 0 70px -20px rgba(70,150,255,.75), inset 160px 0 160px -80px rgba(30,90,200,.45), -20px 0 90px rgba(60,130,255,.35)",
        }} />

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
