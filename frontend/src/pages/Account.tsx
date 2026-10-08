// Account: sign in or sign up with Google, choose the places you follow, test your email, link WhatsApp, review what we sent.
// Replay alerts are labelled simulated here and in the email itself.
import { useMemo, useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { BellIcon, CheckIcon, MailIcon, MapPinIcon, MessageCircleIcon, ShieldCheckIcon, XIcon } from "lucide-react"
import { toast } from "sonner"
import { account, token, useMe, useSignOut, type Delivery, type Me } from "@/api/account"
import { useRegionZones } from "@/api/hooks"
import { AppShell } from "@/components/app-shell"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"

const REGION_ID = "1"
const initials = (m: Me) => (m.name || m.email).split(/[\s@.]+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("")

const ERRORS: Record<string, string> = {
  signin_failed: "We could not verify your Google sign-in. Please try again.",
  cancelled: "Sign-in was cancelled.",
}

// Returning from Google: the backend put our token in the URL fragment (never sent to a server). Move it to storage and clear the URL.
function takeCallback(): { error: string | null; isNew: boolean } {
  const f = new URLSearchParams(window.location.hash.slice(1))
  const t = f.get("token")
  const error = new URLSearchParams(window.location.search).get("error")
  if (t) token.set(t)
  if (t || error) window.history.replaceState(null, "", window.location.pathname)
  return { error, isNew: f.get("new") === "1" }
}

function GoogleG() {
  return (
    <svg viewBox="0 0 48 48" className="size-5" aria-hidden>
      <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.8 2.4 30.3 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.9 6.1C12.4 13.6 17.7 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.1 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.4c-.5 2.9-2.1 5.3-4.5 7l7.3 5.7c4.3-4 6.9-9.9 6.9-17.2z" />
      <path fill="#FBBC05" d="M10.5 28.7c-.5-1.4-.8-3-.8-4.7s.3-3.2.8-4.7l-7.9-6.1C.9 16.4 0 20.1 0 24s.9 7.6 2.6 10.8l7.9-6.1z" />
      <path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.3-5.7c-2 1.4-4.7 2.3-8.6 2.3-6.3 0-11.6-4.1-13.5-9.8l-7.9 6.1C6.5 42.6 14.6 48 24 48z" />
    </svg>
  )
}

function SignIn({ error }: { error: string | null }) {
  const cfg = useQuery({ queryKey: ["auth-config"], queryFn: account.config, retry: 1 })
  return (
    <div className="mx-auto w-full max-w-md pt-6 md:pt-16">
      <Card>
        <CardHeader className="text-center">
          <div className="mx-auto mb-2 flex size-12 items-center justify-center rounded-full bg-muted"><BellIcon className="size-6" /></div>
          <CardTitle className="text-xl">Flood alerts for your neighbourhood</CardTitle>
          <CardDescription>Sign in or create an account in one step. Follow the places you care about and we email you when they reach the alert level or an official warning is issued.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {error && <p role="alert" className="rounded border border-destructive/40 bg-destructive/10 p-2 text-center text-sm text-destructive">{ERRORS[error] ?? "Sign-in failed."}</p>}
          {cfg.isLoading && <p className="text-center text-sm text-muted-foreground">Loading…</p>}
          {cfg.isError && <p className="text-center text-sm text-destructive">Could not reach the server. Is the API running?</p>}
          {cfg.data && !cfg.data.enabled && <p className="text-center text-sm text-muted-foreground">Accounts are not configured on this server.</p>}
          {cfg.data?.providers.map((p) => (
            <Button key={p.id} render={<a href={p.login_url} />} size="lg" variant="outline" className="w-full gap-3">
              <GoogleG /> Continue with {p.label}
            </Button>
          ))}
          <ul className="space-y-1.5 text-xs text-muted-foreground">
            <li className="flex gap-2"><ShieldCheckIcon className="mt-0.5 size-3.5 shrink-0" /> We only read your name and verified email. No password is created or stored.</li>
            <li className="flex gap-2"><MailIcon className="mt-0.5 size-3.5 shrink-0" /> Replay alerts are marked simulated. Official warnings are marked official.</li>
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}

function Places({ me }: { me: Me }) {
  const qc = useQueryClient()
  const zones = useRegionZones(REGION_ID)
  const [picked, setPicked] = useState<Set<string>>(new Set(me.zone_ids))
  const [q, setQ] = useState("")
  const [saving, setSaving] = useState(false)
  const all = useMemo(() => [...(zones.data ?? [])].sort((a, b) => a.name.localeCompare(b.name)), [zones.data])
  const byId = useMemo(() => new Map(all.map((z) => [z.id, z])), [all])
  const counties = useMemo(() => [...new Set(all.map((z) => z.county).filter((c): c is string => !!c))].sort(), [all])
  const list = all.filter((z) => z.name.toLowerCase().includes(q.toLowerCase()))
  const dirty = picked.size !== me.zone_ids.length || me.zone_ids.some((id) => !picked.has(id))

  const toggle = (id: string, on: boolean) => setPicked((s) => { const n = new Set(s); if (on) n.add(id); else n.delete(id); return n })
  const addCounty = (c: string) => setPicked((s) => new Set([...s, ...all.filter((z) => z.county === c).map((z) => z.id)]))
  const save = async () => {
    setSaving(true)
    try {
      await account.setZones([...picked])
      await qc.invalidateQueries({ queryKey: ["me"] })
      toast.success(picked.size ? `Following ${picked.size} place${picked.size === 1 ? "" : "s"}` : "You are not following any places")
    } catch {
      toast.error("Could not save your places. Please sign in again.")
    } finally {
      setSaving(false)
    }
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><MapPinIcon className="size-4" /> Places you follow</CardTitle>
        <CardDescription>Alerts are only sent for these places. {picked.size === 0 && "You are not following any places yet."}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {picked.size > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {[...picked].map((id) => (
              <Badge key={id} variant="secondary" className="gap-1 pr-1">
                {byId.get(id)?.name ?? id}
                <button type="button" aria-label={`Stop following ${byId.get(id)?.name ?? id}`} onClick={() => toggle(id, false)} className="rounded-full p-0.5 hover:bg-background/60"><XIcon className="size-3" /></button>
              </Badge>
            ))}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <Input className="max-w-60" placeholder="Search places" value={q} onChange={(e) => setQ(e.target.value)} />
          {counties.map((c) => <Button key={c} type="button" size="sm" variant="outline" onClick={() => addCounty(c)}>Add all {c}</Button>)}
          {picked.size > 0 && <Button type="button" size="sm" variant="ghost" onClick={() => setPicked(new Set())}>Clear</Button>}
        </div>
        {zones.isLoading && <p className="text-sm text-muted-foreground">Loading places…</p>}
        <div className="grid max-h-72 grid-cols-1 gap-1 overflow-y-auto sm:grid-cols-2">
          {list.map((z) => (
            <label key={z.id} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm hover:bg-muted">
              <Checkbox checked={picked.has(z.id)} onCheckedChange={(c) => toggle(z.id, c === true)} />
              <span>{z.name}</span>
              <span className="ml-auto text-xs text-muted-foreground">{z.county}</span>
            </label>
          ))}
          {!zones.isLoading && list.length === 0 && <p className="text-sm text-muted-foreground">No places match "{q}".</p>}
        </div>
        <div className="flex items-center gap-3">
          <Button onClick={save} disabled={!dirty || saving}>{saving ? "Saving…" : "Save places"}</Button>
          {dirty && !saving && <span className="text-sm text-muted-foreground">Unsaved changes</span>}
        </div>
      </CardContent>
    </Card>
  )
}

function Notifications({ me }: { me: Me }) {
  const qc = useQueryClient()
  const [busy, setBusy] = useState(false)
  const setPrefs = async (on: boolean) => {
    try {
      await account.setPrefs(on)
      await qc.invalidateQueries({ queryKey: ["me"] })
      toast(on ? "Email alerts on" : "Email alerts off. Alerts still appear below.")
    } catch {
      toast.error("Could not update your preference.")
    }
  }
  const test = async () => {
    setBusy(true)
    try {
      const r = await account.testEmail()
      if (r.status === "sent") toast.success(`Test email sent to ${r.to}. Check your spam folder if it does not arrive.`)
      else if (r.status === "outbox") toast(`Email sending is not configured on this server. The test message was saved to its outbox.`)
      else toast.error("The server could not send the email. Check its SMTP settings.")
    } catch (e) {
      toast.error(String(e).includes("429") ? "Please wait a minute before sending another test." : "Could not send the test email.")
    } finally {
      setBusy(false)
    }
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><MailIcon className="size-4" /> Email notifications</CardTitle>
        <CardDescription>Sent to {me.email}. New alerts are grouped into one email.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-row flex-wrap items-center gap-4">
        <label className="flex items-center gap-2 text-sm">
          <Checkbox checked={me.email_alerts} onCheckedChange={(c) => setPrefs(c === true)} />
          Email me alerts
        </label>
        <Button variant="outline" size="sm" onClick={test} disabled={busy}>{busy ? "Sending…" : "Send a test email"}</Button>
      </CardContent>
    </Card>
  )
}

const WA_ERRORS: Record<string, string> = {
  "422": "That does not look right. Use the full number with country code, or check the code.",
  "429": "Please wait a minute before asking for another code.",
  "410": "That code expired. Ask for a new one.",
  "502": "We could not message that number. Is it on WhatsApp?",
  "503": "WhatsApp is not connected on this server right now.",
}

function WhatsApp({ me }: { me: Me }) {
  const qc = useQueryClient()
  const [number, setNumber] = useState("")
  const [sentTo, setSentTo] = useState<string | null>(null)
  const [code, setCode] = useState("")
  const [busy, setBusy] = useState(false)
  const run = async (f: () => Promise<unknown>, ok: string) => {
    setBusy(true)
    try {
      await f()
      toast.success(ok)
    } catch (e) {
      toast.error(WA_ERRORS[(e as Error).message] ?? "Something went wrong. Please try again.")
    } finally {
      setBusy(false)
    }
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><MessageCircleIcon className="size-4" /> WhatsApp notifications</CardTitle>
        <CardDescription>
          {me.whatsapp ? `Alerts also go to +${me.whatsapp} on WhatsApp.` : "Get the same alerts on WhatsApp. We send a code to check the number is yours."}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-row flex-wrap items-center gap-3">
        {me.whatsapp ? (
          <Button variant="outline" size="sm" disabled={busy}
            onClick={() => run(async () => { await account.whatsappRemove(); await qc.invalidateQueries({ queryKey: ["me"] }) }, "WhatsApp alerts off")}>
            Stop WhatsApp alerts
          </Button>
        ) : sentTo ? (
          <form className="flex flex-wrap items-center gap-2" onSubmit={(e) => {
            e.preventDefault()
            run(async () => { await account.whatsappVerify(code); setSentTo(null); setCode(""); await qc.invalidateQueries({ queryKey: ["me"] }) }, "WhatsApp alerts on")
          }}>
            <Input className="w-32" inputMode="numeric" autoComplete="one-time-code" maxLength={6} placeholder="6-digit code"
              aria-label="Code sent on WhatsApp" value={code} onChange={(e) => setCode(e.target.value)} />
            <Button size="sm" type="submit" disabled={busy || code.trim().length !== 6}>Confirm</Button>
            <Button size="sm" variant="ghost" type="button" onClick={() => setSentTo(null)}>Use another number</Button>
            <span className="text-sm text-muted-foreground">Code sent to +{sentTo}</span>
          </form>
        ) : (
          <form className="flex flex-wrap items-center gap-2" onSubmit={(e) => {
            e.preventDefault()
            run(async () => setSentTo((await account.whatsappStart(number)).sent_to), "Code sent. Check WhatsApp.")
          }}>
            <Input className="w-56" type="tel" autoComplete="tel" placeholder="+1 305 555 0100" aria-label="WhatsApp number with country code"
              value={number} onChange={(e) => setNumber(e.target.value)} />
            <Button size="sm" type="submit" disabled={busy || !number.trim()}>{busy ? "Sending…" : "Send code"}</Button>
          </form>
        )}
      </CardContent>
    </Card>
  )
}

const STATUS: Record<string, string> = {
  sent: "Emailed", outbox: "Saved (email not configured)", muted: "In-app only", failed: "Email failed",
  wa_sent: "WhatsApp sent", wa_failed: "WhatsApp failed",
}

function History() {
  const q = useQuery({ queryKey: ["my-alerts"], queryFn: account.alerts, refetchInterval: 30000 })
  const items: Delivery[] = q.data ?? []
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><BellIcon className="size-4" /> Alert history</CardTitle>
        <CardDescription>Everything we notified you about, newest first.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {q.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {!q.isLoading && items.length === 0 && <p className="text-sm text-muted-foreground">No alerts yet. When a place you follow reaches the alert level, or an official warning covers its county, it shows up here.</p>}
        {items.map((a) => (
          <div key={a.id} className="rounded border p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={a.kind === "live" ? "default" : "outline"}>{a.kind === "live" ? "Official" : "Simulated replay"}</Badge>
              <span className="font-medium">{a.title}</span>
              <span className="ml-auto text-xs text-muted-foreground">{new Date(a.created_at).toLocaleString()}</span>
            </div>
            <p className="mt-1 whitespace-pre-line text-muted-foreground">{a.body}</p>
            <p className="mt-1 text-xs text-muted-foreground">{a.status.split("+").map((st) => STATUS[st] ?? st).join(" · ")}</p>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

function DangerZone({ onDeleted }: { onDeleted: () => void }) {
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  const del = async () => {
    setBusy(true)
    try {
      await account.remove()
      onDeleted()
    } catch {
      toast.error("Could not delete your account. Please try again.")
      setBusy(false)
    }
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>Delete account</CardTitle>
        <CardDescription>Removes your account, followed places and alert history. This cannot be undone.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-row items-center gap-2">
        {!confirm ? (
          <Button variant="outline" className="text-destructive" onClick={() => setConfirm(true)}>Delete my account</Button>
        ) : (
          <>
            <Button variant="outline" className="border-destructive text-destructive" onClick={del} disabled={busy}>{busy ? "Deleting…" : "Yes, delete everything"}</Button>
            <Button variant="ghost" onClick={() => setConfirm(false)} disabled={busy}>Cancel</Button>
          </>
        )}
      </CardContent>
    </Card>
  )
}

export default function Account() {
  const [cb] = useState(takeCallback)
  const me = useMe()
  const signOut = useSignOut()
  const u = me.data

  return (
    <AppShell>
      <div className="flex flex-col gap-4 p-4 md:p-6">
        {me.isLoading ? (
          <p className="text-sm text-muted-foreground">Signing you in…</p>
        ) : !u ? (
          <SignIn error={cb.error} />
        ) : (
          <>
            {cb.isNew && u.zone_ids.length === 0 && (
              <p className="flex items-center gap-2 rounded border bg-muted/40 p-3 text-sm"><CheckIcon className="size-4" /> Welcome, {u.name || "there"}! Your account is ready. Choose the places you want alerts for below.</p>
            )}
            <Card>
              <CardContent className="flex flex-row flex-wrap items-center gap-4 pt-6">
                <Avatar className="size-14"><AvatarFallback className="text-lg">{initials(u)}</AvatarFallback></Avatar>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-lg font-semibold">{u.name || u.email}</p>
                  <p className="truncate text-sm text-muted-foreground">{u.email}</p>
                  <div className="mt-2 flex gap-2">
                    <Badge variant="outline">{u.zone_ids.length} place{u.zone_ids.length === 1 ? "" : "s"} followed</Badge>
                    <Badge variant={u.email_alerts ? "secondary" : "outline"}>{u.email_alerts ? "Email alerts on" : "Email alerts off"}</Badge>
                  </div>
                </div>
                <Button variant="outline" onClick={signOut}>Sign out</Button>
              </CardContent>
            </Card>
            <Notifications me={u} />
            {u.whatsapp_available && <WhatsApp me={u} />}
            <Places key={u.zone_ids.join(",")} me={u} />
            <History />
            <DangerZone onDeleted={() => { signOut(); toast("Your account was deleted") }} />
          </>
        )}
      </div>
    </AppShell>
  )
}
