import { Reveal } from "../common/Reveal";

export function FeatureGrid() {
  const items = [
    {
      title: "Discovery",
      desc: "Continuously map data across apps, logs, DBs, and cloud storage to restore visibility.",
      emoji: "🧭",
    },
    {
      title: "Classification",
      desc: "Detect PII and sensitive categories (health, finance) with AI-driven labeling.",
      emoji: "🔎",
    },
    {
      title: "Remediation",
      desc: "Anonymize, minimize, and automate consent workflows to reduce exposure.",
      emoji: "🧹",
    },
    {
      title: "Monitoring",
      desc: "Continuous compliance checks with alerts and reports aligned to GDPR.",
      emoji: "📈",
    },
  ];

  return (
    <div className="container-max py-16 content-auto" id="features">
      <Reveal className="text-center" as="div">
        <h2 className="text-2xl sm:text-3xl font-bold text-slate-900">Core capabilities</h2>
        <p className="mt-3 text-slate-600 max-w-2xl mx-auto">
          Proactive privacy protection tailored for Nordic identity ecosystems and EU data law.
        </p>
      </Reveal>
  <div className="mt-10 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6 items-stretch">
        {items.map((f, i) => (
          <Reveal key={f.title} delayMs={i * 90} className="h-full">
            <div className="h-full rounded-xl border border-slate-200 bg-white/80 p-6 shadow-sm transition-transform duration-300 hover:-translate-y-0.5 flex flex-col">
              <div className="text-3xl">{f.emoji}</div>
              <h3 className="mt-3 font-semibold text-slate-900">{f.title}</h3>
              <p className="mt-2 text-sm text-slate-600">
                {f.desc}
              </p>
              {/* Spacer to ensure consistent padding at bottom when descriptions vary */}
              <div className="mt-auto" />
            </div>
          </Reveal>
        ))}
      </div>
    </div>
  );
}
