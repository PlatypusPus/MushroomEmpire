import Link from 'next/link';
import { Navbar } from '../components/Navbar';
import { FeatureGrid } from '../components/landing/FeatureGrid';
import { AgentsOverview } from '../components/landing/AgentsOverview';
import { Steps } from '../components/landing/Steps';
import { Footer } from '../components/landing/Footer';

export default function HomePage() {
  return (
    <main className="min-h-screen flex flex-col">
      <Navbar />
      <section className="relative pt-20 pb-24 overflow-hidden">
        <div className="absolute inset-0 pointer-events-none overflow-hidden">
          <div className="absolute -top-24 left-1/2 -translate-x-1/2 w-[480px] h-[480px] md:w-[560px] md:h-[560px] rounded-full bg-gradient-to-br from-brand-200/50 to-brand-400/30 blur-xl opacity-60 animate-drift-slow transform-gpu" />
          <div className="hidden md:block absolute top-10 right-[10%] w-[340px] h-[340px] rounded-full bg-gradient-to-br from-brand-300/40 to-brand-500/25 blur-xl opacity-50 animate-drift-slower transform-gpu" />
          <div className="hidden md:block absolute -bottom-28 left-[8%] w-[300px] h-[300px] rounded-full bg-gradient-to-br from-brand-100/60 to-brand-300/35 blur-xl opacity-60 animate-drift-slower transform-gpu" style={{ animationDelay: '1.2s' }} />
        </div>
        <div className="container-max relative text-center">
          <div className="mx-auto max-w-3xl">
            <h1 className="text-4xl sm:text-5xl md:text-6xl font-extrabold tracking-tight text-slate-900">
              ShroomShield
            </h1>
            <p className="mt-6 text-base sm:text-lg text-slate-700">
              AI agents that discover, classify, and remediate personal data across your ecosystem—built for BankID, MitID, and Suomi.fi contexts.
            </p>
            <div className="mt-8 flex flex-wrap items-center justify-center gap-3 sm:gap-4">
              <Link href="/try" className="inline-flex items-center rounded-md bg-brand-600 px-7 py-3 text-white font-semibold shadow-lg hover:bg-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-400 focus:ring-offset-2">
                Start free scan
              </Link>
              <Link href="#features" className="inline-flex items-center rounded-md border border-slate-300 px-7 py-3 text-slate-700 font-medium hover:bg-white/60 focus:outline-none focus:ring-2 focus:ring-brand-400 focus:ring-offset-2">
                Explore features
              </Link>
            </div>
            <div className="mt-10 grid grid-cols-3 gap-3 sm:gap-6 text-center text-xs sm:text-sm">
              <div className="flex flex-col"><span className="font-semibold text-slate-900">99%</span><span className="text-slate-600">PII labels coverage*</span></div>
              <div className="flex flex-col"><span className="font-semibold text-slate-900"><span className="align-middle">⚡</span> Real-time</span><span className="text-slate-600">Monitoring</span></div>
              <div className="flex flex-col"><span className="font-semibold text-slate-900">EU-first</span><span className="text-slate-600">Reg alignment</span></div>
            </div>
          </div>
        </div>
      </section>
      <FeatureGrid />
  <Steps />
      <AgentsOverview />
  <section id="contact" className="container-max py-20 content-auto">
        <div className="rounded-2xl border border-brand-200/70 bg-white/80 backdrop-blur p-10 text-center shadow-sm">
          <h2 className="text-2xl font-bold text-slate-900">Ready to pilot?</h2>
          <p className="mt-4 text-slate-600 max-w-xl mx-auto">We’re onboarding early Nordic partners. Get in touch to shape proactive privacy intelligence.</p>
          <div className="mt-6">
            <Link href="/try" className="inline-flex items-center rounded-md bg-brand-600 px-6 py-3 text-white font-semibold shadow hover:bg-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-400 focus:ring-offset-2">
              Request access
            </Link>
          </div>
        </div>
      </section>
      <Footer />
    </main>
  );
}
