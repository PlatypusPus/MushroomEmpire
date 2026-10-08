// Reading list behind the live hazard level: full official texts (NWS alerts, NHC advisories and outlook, NWS Miami forecast discussion),
// each with a preview image. Reading material only: separate from the replay and never a model input.
import { useState } from "react"
import { ExternalLinkIcon, ImageOffIcon, NewspaperIcon } from "lucide-react"

import type { HazardArticle } from "@/api/client"
import { useHazardArticles } from "@/api/hooks"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"

const KIND: Record<HazardArticle["kind"], string> = {
  alert: "Weather warning",
  advisory: "Storm update",
  summary: "Storm summary",
  discussion: "Forecaster notes",
  outlook: "7-day outlook",
  forecast: "Local forecast notes",
  technical: "Storm data",
}
const LEVEL = ["", "Heads-up", "Watch", "Warning", "Emergency"]

function ago(iso: string | null): string {
  if (!iso) return ""
  const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (Number.isNaN(m)) return ""
  if (m < 1) return "just now"
  if (m < 60) return `${m} min ago`
  if (m < 48 * 60) return `${Math.round(m / 60)} h ago`
  return new Date(iso).toLocaleDateString()
}

function Preview({ a, className }: { a: HazardArticle; className?: string }) {
  const [failed, setFailed] = useState(false)
  if (!a.image || failed)
    return (
      <div className={`flex items-center justify-center bg-muted text-muted-foreground ${className ?? ""}`}>
        <ImageOffIcon className="size-6" aria-label="No preview image" />
      </div>
    )
  return <img src={a.image.url} alt={a.image.alt} loading="lazy" onError={() => setFailed(true)} className={`bg-muted object-cover ${className ?? ""}`} />
}

function Badges({ a }: { a: HazardArticle }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <Badge variant={a.kind === "alert" && (a.level ?? 0) >= 3 ? "destructive" : "outline"}>{KIND[a.kind]}</Badge>
      {a.level ? <Badge variant="secondary">{LEVEL[a.level]}</Badge> : null}
      {a.storm ? <Badge variant="secondary">{a.storm}</Badge> : null}
    </div>
  )
}

export function HazardArticles() {
  const q = useHazardArticles()
  const [open, setOpen] = useState<HazardArticle | null>(null)
  const list = q.data?.articles ?? []

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <NewspaperIcon className="size-4" /> What the experts are saying
        </CardTitle>
        <CardDescription>
          The full official text from the National Weather Service and the National Hurricane Center for South Florida. For reading only: it is separate from the storm replay and is not used by our flood forecast.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {q.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {q.error && <p className="text-sm text-muted-foreground">We cannot reach the weather services right now (are you offline?). The storm replay still works.</p>}
        {q.data?.stale && <p className="text-sm text-destructive">These are the last reports we could get. The weather services did not answer just now.</p>}
        {q.data && q.data.partial.length > 0 && !q.data.stale && (
          <p className="text-xs text-muted-foreground">These did not answer: {q.data.partial.join(", ")}. Showing the rest.</p>
        )}
        {q.data && list.length === 0 && !q.error && <p className="text-sm text-muted-foreground">There are no official reports for the area right now.</p>}
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {list.map((a) => (
            <button
              key={a.id}
              type="button"
              onClick={() => setOpen(a)}
              className="flex flex-col overflow-hidden rounded-lg border bg-card text-left transition hover:border-foreground/40 focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Preview a={a} className="aspect-video w-full" />
              <div className="flex flex-1 flex-col gap-2 p-3">
                <Badges a={a} />
                <h3 className="text-sm font-semibold leading-snug">{a.title}</h3>
                <p className="line-clamp-3 text-xs text-muted-foreground">{a.summary}</p>
                <p className="mt-auto pt-1 text-xs text-muted-foreground">
                  {a.source}
                  {a.issued ? ` · ${ago(a.issued)}` : ""}
                </p>
              </div>
            </button>
          ))}
        </div>

        <Dialog open={open !== null} onOpenChange={(o) => !o && setOpen(null)}>
          <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
            {open && (
              <>
                <DialogHeader>
                  <Badges a={open} />
                  <DialogTitle>{open.title}</DialogTitle>
                  <DialogDescription>
                    {open.source}
                    {open.issued ? ` · issued ${new Date(open.issued).toLocaleString()}` : ""}
                    {open.ends ? ` · until ${new Date(open.ends).toLocaleString()}` : ""}
                  </DialogDescription>
                </DialogHeader>
                {open.image && (
                  <figure>
                    <Preview a={open} className="max-h-96 w-full rounded-md object-contain" />
                    <figcaption className="mt-1 text-xs text-muted-foreground">
                      {open.image.alt}. Image: {open.image.credit}.
                    </figcaption>
                  </figure>
                )}
                <pre className="whitespace-pre-wrap break-words rounded-md bg-muted/50 p-3 font-mono text-xs leading-relaxed">{open.body}</pre>
                <Button render={<a href={open.url} target="_blank" rel="noopener noreferrer" />} variant="outline" size="sm" className="w-fit gap-2">
                  Read it on the official site <ExternalLinkIcon className="size-3.5" />
                </Button>
              </>
            )}
          </DialogContent>
        </Dialog>
      </CardContent>
    </Card>
  )
}
