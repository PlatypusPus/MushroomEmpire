// Model validation: held-out metrics exactly as Lane B recorded them in model_runs. Nothing here is recomputed or rounded up.
import { useLiveModel, useMetrics } from "@/api/hooks"
import { AppShell } from "@/components/app-shell"
import { ChartLeadInteractive, type LeadRow } from "@/components/chart-lead-interactive"
import { CalibrationChart, DetectionChart, SimpleBarChart, SkillChart } from "@/components/validation-charts"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

const REGION_ID = "1"
/* eslint-disable @typescript-eslint/no-explicit-any */
const pct = (x: any) => (typeof x === "number" ? `${Math.round(x * 100)}%` : "n/a")
const num = (x: any, d = 2) => (typeof x === "number" ? x.toFixed(d) : "n/a")
const int = (x: any) => (typeof x === "number" ? x.toLocaleString() : "n/a")

function Section({ title, sub, children }: { title: string; sub?: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {sub && <CardDescription>{sub}</CardDescription>}
      </CardHeader>
      <CardContent className="overflow-x-auto">{children}</CardContent>
    </Card>
  )
}

function Table({ head, rows }: { head: string[]; rows: (string | number)[][] }) {
  return (
    <div className="overflow-x-auto">{/* phones: the table scrolls inside its card instead of being cut off */}
    <table className="w-full text-sm tabular-nums">
      <thead>
        <tr className="border-b text-left text-xs text-muted-foreground">
          {head.map((h) => <th key={h} className="py-1.5 pr-4 font-medium">{h}</th>)}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} className="border-b last:border-0">
            {r.map((c, j) => <td key={j} className={`py-1.5 pr-4 ${j === 0 ? "text-left" : ""}`}>{c}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
    </div>
  )
}

const REGION_NAME = { sf: "South Florida", us: "Rest of the US" } as const

/** Live learning: which model each region uses now and what the last daily update did. Separate from the validated numbers below. */
function LiveLearning() {
  const q = useLiveModel()
  if (!q.data) return null
  return (
    <Card>
      <CardHeader>
        <CardTitle>Live learning</CardTitle>
        <CardDescription>
          Every day the model keeps training on new readings from USGS water gauges, starting from the model checked below. It is tested on
          the newest 14 days it did not train on, and replaces the current model only if it is at least 1% more accurate there. These live
          models are experimental: the validated numbers below are for the original model only.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 sm:grid-cols-2">
        {(Object.keys(REGION_NAME) as (keyof typeof REGION_NAME)[]).map((r) => {
          const x = q.data.regions[r]
          const run = x.last_run
          const better = run?.loss_new != null && run.loss_current != null ? Math.round((1 - run.loss_new / run.loss_current) * 100) : null
          return (
            <div key={r} className="rounded-lg border p-3 text-sm">
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold">{REGION_NAME[r]}</span>
                <Badge variant={x.base ? "outline" : "secondary"}>{x.base ? "original model" : "live-trained"}</Badge>
              </div>
              <div className="mt-1 text-xs text-muted-foreground">{x.gauges_tracked} gauge{x.gauges_tracked === 1 ? "" : "s"} followed{x.trained_at ? ` · updated ${new Date(x.trained_at).toLocaleDateString()}` : ""}</div>
              {run ? (
                <p className="mt-2">
                  Last run {new Date(run.at).toLocaleDateString()}:{" "}
                  {run.reason ? run.reason : run.promoted ? `updated, ${better}% more accurate on the last 14 days` : `kept the current model (new one was not ${PROMOTE_PCT}% better)`}
                  <span className="block text-xs text-muted-foreground">{run.n_train.toLocaleString()} training rows · {run.n_eval.toLocaleString()} test rows · {run.gauges} gauges</span>
                </p>
              ) : (
                <p className="mt-2 text-muted-foreground">No learning run yet.</p>
              )}
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}
const PROMOTE_PCT = 1

export default function Validation() {
  const q = useMetrics(REGION_ID)
  const run = q.data?.[0]
  const m: any = run?.metrics ?? {}
  const v = m.validation ?? {}
  const det = v.detection_and_timing ?? {}
  const peak = m.peak_eval?.methods ?? {}
  const rev = m.review?.A ?? {}

  // chart data, straight from the recorded metrics
  const detection = [
    ["All cases", det.all], ["New rise", det.starting_below_mark], ["Already high", det.already_above_mark],
  ].map(([label, d]: any) => ({ case: label, caught: d?.hits ?? 0, falseAlarms: d?.false_alarms ?? 0, missed: d?.misses ?? 0 }))
  const skill = [
    { measure: "Any event in 24 h", model: m.exceed24h_any?.pr_auc_model, persistence: m.exceed24h_any?.pr_auc_persistence },
    { measure: "New onset", model: m.exceed24h_onset_from_below?.pr_auc_model, persistence: m.exceed24h_onset_from_below?.pr_auc_persistence },
  ]
  const byLead: LeadRow[] = [
    ...Object.entries(m.by_lead ?? {}).map(([h, d]: any) => ({
      lead: `${h} h`, errModel: d.mae_model, errPersistence: d.mae_persistence,
      covModel: d.coverage_q10_q90_model, covPersistence: d.coverage_q10_q90_persistence,
    })),
    ...Object.entries(m.horizons ?? {}).map(([h, d]: any) => ({
      lead: `${h} h`, errModel: d.mae_model, errPersistence: d.mae_persistence, covModel: d.coverage_q10_q90,
    })),
  ]
  const peakBars = [
    { label: "Peak model", value: peak.new_peak_model?.mae_h },
    { label: "Old method", value: peak.old_trajectory_argmax?.mae_h },
    { label: "Guess noon", value: peak.fixed_hour?.mae_h },
  ].filter((d) => typeof d.value === "number")
  const onsetBands = Object.entries(v["recall_by_true_onset_band_(starting_below)"] ?? {}).map(([band, d]: any) => ({
    label: band.replace("true_onset_", "in "), value: d.recall,
  }))

  return (
    <AppShell>
      <div className="flex flex-col gap-4 px-4 py-4 md:gap-6 md:py-6 lg:px-6">
        <div>
          <h1 className="text-2xl font-semibold">Model validation</h1>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
            Every number below comes from the years 2020 to 2023 (split S_7). The model never saw those years in training
            (2010 to 2014) or tuning (2015 to 2019). We count a "flood" when a water gauge stays above its usual high mark for 3 or more
            hours. That is not the same as confirmed street flooding. The gauge units are unverified, so we never print water levels.
          </p>
          {run && (
            <div className="mt-2 flex flex-wrap gap-2">
              <Badge variant="outline">model {run.model} {run.version}</Badge>
              <Badge variant="outline">{int(m.rows)} test issue rows</Badge>
              <Badge variant="outline">alert threshold {num(v.fitted_on_S_6?.alert_threshold)} (fitted on 2015 to 2019)</Badge>
            </div>
          )}
        </div>
        <LiveLearning />
        {q.isLoading && <div className="text-sm text-muted-foreground">Loading metrics...</div>}
        {q.error && <div className="text-sm text-destructive">Could not load metrics: {String(q.error)}</div>}
        {!run && !q.isLoading && !q.error && <div className="text-sm text-muted-foreground">No model run recorded for this region.</div>}

        {run && (
          <>
            <Section title="Alerts: hits, misses and false alarms" sub="At the validated alert threshold, event within the next 24 h. Denominators shown.">
              <DetectionChart data={detection} />
              <Table
                head={["Case", "Events", "Caught", "Missed", "False alarms", "Precision", "Recall", "False-alarm rate"]}
                rows={[
                  ["all", "all", det.all], ["water starting below its mark", "new", det.starting_below_mark],
                  ["water already above its mark", "ongoing", det.already_above_mark],
                ].map(([label, , d]: any) => [label, int(d?.events), int(d?.hits), int(d?.misses), int(d?.false_alarms),
                  pct(d?.precision), pct(d?.recall), d?.correct_quiet === 0 ? "n/a (no quiet cases)" : pct(d?.false_alarm_rate)])}
              />
              <p className="mt-2 text-xs text-muted-foreground">
                Catching a <b>new</b> rise (starting below the mark) is the hard case: about half are caught, and about half of those
                alerts are false alarms. Water that is already high is almost always caught.
              </p>
            </Section>

            <div className="grid grid-cols-1 gap-4 md:gap-6 @3xl/main:grid-cols-2 lg:grid-cols-2">
              <Section title="Against a simple baseline" sub="PR-AUC, higher is better. Persistence: assume today's level and trend carry on.">
                <SkillChart data={skill} />
                <Table
                  head={["Measure", "Model", "Persistence", "Base rate"]}
                  rows={[
                    ["PR-AUC, any event in 24 h", num(m.exceed24h_any?.pr_auc_model), num(m.exceed24h_any?.pr_auc_persistence), pct(m.exceed24h_any?.base_rate)],
                    ["PR-AUC, new onset from below", num(m.exceed24h_onset_from_below?.pr_auc_model), num(m.exceed24h_onset_from_below?.pr_auc_persistence), pct(m.exceed24h_onset_from_below?.base_rate)],
                    ["Brier score (lower is better)", num(m.exceed24h_any?.brier_model, 3), num(m.exceed24h_any?.brier_persistence, 3), ""],
                  ]}
                />
              </Section>

              <Section title="Calibration" sub="When we say 50%, does it happen about half the time? Dots on the dashed line are perfect.">
                <CalibrationChart data={v.probability?.reliability_calibrated ?? []} />
                <details className="mt-2 text-sm">
                  <summary className="cursor-pointer text-xs text-muted-foreground">Show the numbers</summary>
                  <Table
                    head={["Predicted band", "Cases", "Predicted", "Observed"]}
                    rows={(v.probability?.reliability_calibrated ?? []).map((b: any) => [b.bin, int(b.n), pct(b.predicted), pct(b.observed)])}
                  />
                </details>
                <p className="mt-2 text-xs text-muted-foreground">
                  Expected calibration error {num(v.probability?.ece_calibrated, 3)} after calibration (was {num(v.probability?.ece_raw, 3)}).
                  High water happened slightly less often in these test years than we predicted.
                </p>
              </Section>
            </div>

            <ChartLeadInteractive data={byLead} />
            <details className="-mt-2 px-1 text-sm">
              <summary className="cursor-pointer text-xs text-muted-foreground">Show the numbers by lead</summary>
              <Table
                head={["Lead", "Model error", "Persistence error", "Model q10 to q90 coverage (target 80%)"]}
                rows={byLead.map((r) => [r.lead, num(r.errModel), num(r.errPersistence), pct(r.covModel)])}
              />
            </details>

            <div className="grid grid-cols-1 gap-4 md:gap-6 lg:grid-cols-2">
              <Section title="Timing" sub="Hours off, for events that were caught. Lower is better.">
                <SimpleBarChart data={peakBars} unit="h" label="Mean peak-time error" />
                <div className="mt-2 text-xs font-medium text-muted-foreground">New rises caught, by how far ahead they start</div>
                <SimpleBarChart data={onsetBands} unit="%" label="Caught" />
                <Table
                  head={["What", "Mean error", "Typical (median)", "Notes"]}
                  rows={[
                    ["Onset", `${num(det.all?.onset_err_h_mae, 1)} h`, `${num(det.all?.onset_err_h_median, 0)} h`, `90% within ${num(det.all?.onset_err_h_p90_abs, 0)} h`],
                    ["Peak, dedicated peak model", `${num(peak.new_peak_model?.mae_h, 1)} h`, `${num(peak.new_peak_model?.median_ae_h, 0)} h`, `${pct(peak.new_peak_model?.within_3h)} within 3 h`],
                    ["Peak, old method", `${num(peak.old_trajectory_argmax?.mae_h, 1)} h`, `${num(peak.old_trajectory_argmax?.median_ae_h, 0)} h`, "replaced: no better than guessing"],
                    ["Peak, always guess noon", `${num(peak.fixed_hour?.mae_h, 1)} h`, `${num(peak.fixed_hour?.median_ae_h, 0)} h`, "the bar to beat"],
                  ]}
                />
                <p className="mt-2 text-xs text-muted-foreground">
                  New onsets further ahead are harder: caught{" "}
                  {Object.entries(v["recall_by_true_onset_band_(starting_below)"] ?? {})
                    .map(([band, d]: any) => `${pct(d.recall)} at ${band.replace("true_onset_", "")}`).join(", ")}.
                </p>
              </Section>

              <Section title="Against real flood reports" sub="SFBench flood observation reports inside our zones, holdout storms. Positives only.">
                <Table
                  head={["Measure", "Value"]}
                  rows={[
                    ["Reports we could assess", int(rev.assessable_reports)],
                    ["Reports with an alert covering them", pct(rev.share_of_reports_with_an_alert_covering_them)],
                    ["All zone-times alerted in the same storm windows", pct(rev.share_of_all_zone_issues_alerted_in_same_windows)],
                    ["Lift over alerting at random", `${num(rev.lift_vs_all_zone_issues, 1)} x`],
                    ["Ranking: reported zone-days above others (AUC)", num(rev.zone_day_ranking_auc_reported_vs_not)],
                  ]}
                />
                <p className="mt-2 text-xs text-muted-foreground">
                  Almost every report is covered, but during storms we alert broadly, so coverage alone flatters us; the lift and
                  ranking AUC are the fairer numbers. Reports have no "no flood" records, so they cannot measure false alarms.
                </p>
              </Section>
            </div>

            <div className="grid grid-cols-1 gap-4 md:gap-6 lg:grid-cols-2">
              <Section title="Severity classes" sub="Weak beyond low: prefer wording like 'higher than usual'.">
                <Table
                  head={["Class", "Real cases", "Precision", "Recall"]}
                  rows={Object.entries(v.severity?.per_class ?? {}).map(([c, d]: any) => [c, int(d.true_n), pct(d.precision), pct(d.recall)])}
                />
                <p className="mt-2 text-xs text-muted-foreground">
                  {pct(v.severity?.within_one_class)} of cases land within one class of the truth.
                </p>
              </Section>

              <Section title="Gauges the model never saw" sub="Spatial cross-validation: whole gauges held out.">
                <Table
                  head={["Measure", "Unseen gauges", "Seen gauges"]}
                  rows={[
                    ["PR-AUC, any event", num(m.spatial?.mean_unseen?.any_pr_auc), num(m.spatial?.mean_shipped_seen?.any_pr_auc)],
                    ["PR-AUC, new onset", num(m.spatial?.mean_unseen?.onset_pr_auc), num(m.spatial?.mean_shipped_seen?.onset_pr_auc)],
                  ]}
                />
              </Section>
            </div>

            <Section title="Known limits">
              <ul className="list-disc space-y-1 pl-5 text-sm">
                <li>A "flood" here means a gauge above its usual high mark, about 18 times per gauge per year. It is not confirmed street flooding.</li>
                <li>29 of 109 zones have no usable water gauge and always show as not enough data, never as low risk.</li>
                <li>No tide or surge input in the shipped forecaster, so coastal surge events can be under-forecast.</li>
                <li>Gauge timestamps have an unverified timezone; times show the stored gauge clock.</li>
                <li>Shelters are OSM schools and community centres marked as potential, not an official shelter list.</li>
                <li>The live hazard panel (NWS, NHC) is a separate live feed and is not an input to this model.</li>
              </ul>
            </Section>
          </>
        )}
      </div>
    </AppShell>
  )
}
