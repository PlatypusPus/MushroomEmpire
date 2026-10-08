// Account: Google sign-in, choose the places you follow, see the alerts we sent. Replay alerts are labelled simulated in the email and here.
import { useEffect, useRef, useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { account, token, type Me } from "@/api/account"
import { useRegionZones } from "@/api/hooks"
import { AppShell } from "@/components/app-shell"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"

const REGION_ID = "1"

declare global {
  interface Window { google?: { accounts: { id: { initialize: (c: object) => void; renderButton: (el: HTMLElement, o: object) => void } } } }
}

function GoogleButton({ clientId, onCredential }: { clientId: string; onCredential: (c: string) => void }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const render = () => {
      if (!window.google || !ref.current) return
      window.google.accounts.id.initialize({ client_id: clientId, callback: (r: { credential: string }) => onCredential(r.credential) })
      window.google.accounts.id.renderButton(ref.current, { theme: "filled_black", size: "large", shape: "pill", text: "continue_with" })
    }
    if (window.google) return render()
    const s = document.createElement("script")
    s.src = "https://accounts.google.com/gsi/client"
    s.async = true
    s.onload = render
    document.head.appendChild(s)
  }, [clientId, onCredential])
  return <div ref={ref} />
}

function SignIn({ onSignedIn }: { onSignedIn: () => void }) {
  const cfg = useQuery({ queryKey: ["auth-config"], queryFn: account.config, retry: 1 })
  const [err, setErr] = useState<string | null>(null)
  const login = async (credential: string) => {
    try {
      token.set((await account.google(credential)).token)
      onSignedIn()
    } catch {
      setErr("Google sign-in could not be verified. Try again.")
    }
  }
  return (
    <Card className="max-w-md">
      <CardHeader>
        <CardTitle>Get flood alerts by email</CardTitle>
        <CardDescription>Sign in with Google, pick the places you care about, and we email you when they cross the alert threshold or an official warning is issued.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {cfg.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {cfg.isError && <p className="text-sm text-destructive">Could not reach the API.</p>}
        {cfg.data && !cfg.data.enabled && <p className="text-sm text-muted-foreground">Accounts are not configured on this server (set GOOGLE_CLIENT_ID and JWT_SECRET).</p>}
        {cfg.data?.enabled && <GoogleButton clientId={cfg.data.google_client_id} onCredential={login} />}
        {err && <p className="text-sm text-destructive">{err}</p>}
      </CardContent>
    </Card>
  )
}

function Places({ me }: { me: Me }) {
  const qc = useQueryClient()
  const zones = useRegionZones(REGION_ID)
  const [picked, setPicked] = useState<Set<string>>(new Set(me.zone_ids))
  const [q, setQ] = useState("")
  const [saved, setSaved] = useState<string | null>(null)
  const list = (zones.data ?? []).filter((z) => z.name.toLowerCase().includes(q.toLowerCase())).sort((a, b) => a.name.localeCompare(b.name))
  const toggle = (id: string, on: boolean) => setPicked((s) => { const n = new Set(s); if (on) n.add(id); else n.delete(id); return n })
  const save = async () => {
    try {
      await account.setZones([...picked])
      await qc.invalidateQueries({ queryKey: ["me"] })
      setSaved("Saved")
    } catch {
      setSaved("Could not save. Sign in again.")
    }
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>Places you follow</CardTitle>
        <CardDescription>{picked.size} selected. Alerts are only sent for these places.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Input placeholder="Search places" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="grid max-h-80 grid-cols-1 gap-1 overflow-y-auto sm:grid-cols-2">
          {list.map((z) => (
            <label key={z.id} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm hover:bg-muted">
              <Checkbox checked={picked.has(z.id)} onCheckedChange={(c) => toggle(z.id, c === true)} />
              <span>{z.name}</span>
              <span className="ml-auto text-xs text-muted-foreground">{z.county}</span>
            </label>
          ))}
        </div>
        <div className="flex items-center gap-3">
          <Button onClick={save}>Save places</Button>
          {saved && <span className="text-sm text-muted-foreground">{saved}</span>}
        </div>
      </CardContent>
    </Card>
  )
}

function Inbox() {
  const q = useQuery({ queryKey: ["my-alerts"], queryFn: account.alerts, refetchInterval: 30000 })
  return (
    <Card>
      <CardHeader>
        <CardTitle>Your alerts</CardTitle>
        <CardDescription>Everything we notified you about, newest first.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {q.data?.length === 0 && <p className="text-sm text-muted-foreground">Nothing yet.</p>}
        {q.data?.map((a) => (
          <div key={a.id} className="rounded border p-3 text-sm">
            <div className="flex items-center gap-2">
              <Badge variant={a.kind === "live" ? "default" : "outline"}>{a.kind === "live" ? "Official" : "Simulated replay"}</Badge>
              <span className="font-medium">{a.title}</span>
              <span className="ml-auto text-xs text-muted-foreground">{new Date(a.created_at).toLocaleString()}</span>
            </div>
            <p className="mt-1 whitespace-pre-line text-muted-foreground">{a.body}</p>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

export default function Account() {
  const qc = useQueryClient()
  const [signedIn, setSignedIn] = useState(() => token.get() != null)
  const me = useQuery({ queryKey: ["me"], queryFn: account.me, enabled: signedIn, retry: false })
  useEffect(() => { if (me.isError) setSignedIn(false) }, [me.isError])

  const out = () => { token.clear(); setSignedIn(false); qc.clear() }
  const del = async () => { if (confirm("Delete your account and all alert history?")) { await account.remove(); out() } }

  return (
    <AppShell>
      <div className="flex flex-col gap-4 p-4 md:p-6">
        {!signedIn || !me.data ? (
          signedIn ? <p className="text-sm text-muted-foreground">Loading…</p> : <SignIn onSignedIn={() => { setSignedIn(true); qc.invalidateQueries({ queryKey: ["me"] }) }} />
        ) : (
          <>
            <Card>
              <CardHeader>
                <CardTitle>{me.data.name || me.data.email}</CardTitle>
                <CardDescription>{me.data.email}</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-wrap items-center gap-4">
                <label className="flex items-center gap-2 text-sm">
                  <Checkbox
                    checked={me.data.email_alerts}
                    onCheckedChange={async (c) => { await account.setPrefs(c === true); qc.invalidateQueries({ queryKey: ["me"] }) }}
                  />
                  Email me alerts
                </label>
                <Button variant="outline" onClick={out}>Sign out</Button>
                <Button variant="ghost" className="text-destructive" onClick={del}>Delete account</Button>
              </CardContent>
            </Card>
            <Places key={me.data.zone_ids.join(",")} me={me.data} />
            <Inbox />
          </>
        )}
      </div>
    </AppShell>
  )
}
