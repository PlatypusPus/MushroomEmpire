// SHROOMCAST WhatsApp bridge: links ONE phone (yours) through WhatsApp Web via Baileys and exposes a tiny
// localhost HTTP API the backend calls to message users who verified their number on the Account page.
//   GET  /status                      -> { connected, me }
//   POST /send  { to, text }          -> { ok: true } | 4xx/5xx { error }
//   GET  /qr?token=$BRIDGE_TOKEN       -> browser page with the live QR to scan (refreshes itself)
// The API needs "Authorization: Bearer $BRIDGE_TOKEN" (npm start reads it from ./.env). Scan the QR from the terminal
// or /qr (WhatsApp > Linked devices > Link a device). The session lives in ./auth, so you scan only once.
import http from "node:http"
import makeWASocket, { DisconnectReason, fetchLatestBaileysVersion, useMultiFileAuthState } from "@whiskeysockets/baileys"
import pino from "pino"
import QR from "qrcode"
import qrcode from "qrcode-terminal"

const PORT = +(process.env.BRIDGE_PORT ?? 8787)
const TOKEN = process.env.BRIDGE_TOKEN
if (!TOKEN) { console.error("Set BRIDGE_TOKEN (same value as WHATSAPP_BRIDGE_TOKEN in backend/.env)"); process.exit(1) }

let sock = null
let connected = false
let lastQr = null // current pairing QR; WhatsApp rotates it every ~20 s until scanned

async function connect() {
  const { state, saveCreds } = await useMultiFileAuthState("auth")
  const { version } = await fetchLatestBaileysVersion()
  sock = makeWASocket({ version, auth: state, logger: pino({ level: "warn" }) })
  sock.ev.on("creds.update", saveCreds)
  sock.ev.on("connection.update", ({ connection, lastDisconnect, qr }) => {
    if (qr) { lastQr = qr; console.log("Scan with WhatsApp > Linked devices > Link a device:"); qrcode.generate(qr, { small: true }) }
    if (connection === "open") { connected = true; lastQr = null; console.log(`WhatsApp linked as ${sock.user?.id}`) }
    if (connection === "close") {
      connected = false
      const code = lastDisconnect?.error?.output?.statusCode
      if (code === DisconnectReason.loggedOut) { console.error("Logged out from the phone. Delete ./auth and restart to link again."); process.exit(1) }
      setTimeout(connect, 3000) // ponytail: fixed 3 s retry, add backoff if WhatsApp starts rate-limiting reconnects
    }
  })
}

const json = (res, code, body) => { res.writeHead(code, { "Content-Type": "application/json" }); res.end(JSON.stringify(body)) }

async function qrPage(res) {
  const body = connected
    ? `<h1>Linked</h1><p>WhatsApp is connected as ${sock.user?.id?.split(":")[0].split("@")[0]}. You can close this page.</p>`
    : lastQr
      ? `<h1>Scan with WhatsApp</h1><p>On your phone: WhatsApp &gt; Settings &gt; Linked devices &gt; Link a device.</p>${await QR.toString(lastQr, { type: "svg", margin: 2, width: 320 })}`
      : "<h1>Waiting for WhatsApp…</h1>"
  res.writeHead(200, { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" })
  res.end(`<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="${connected ? 60 : 5}"><title>SHROOMCAST WhatsApp</title>
<body style="font-family:system-ui;text-align:center;padding:2rem;background:#fff;color:#111">${body}</body>`)
}

http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://x")
  if (req.method === "GET" && url.pathname === "/qr") return url.searchParams.get("token") === TOKEN ? qrPage(res) : json(res, 401, { error: "bad token" })
  if (req.headers.authorization !== `Bearer ${TOKEN}`) return json(res, 401, { error: "bad token" })
  if (req.method === "GET" && req.url === "/status") return json(res, 200, { connected, me: sock?.user?.id ?? null })
  if (req.method !== "POST" || req.url !== "/send") return json(res, 404, { error: "not found" })
  let raw = ""
  for await (const chunk of req) { raw += chunk; if (raw.length > 16_000) return json(res, 413, { error: "too large" }) }
  let to, text
  try { ({ to, text } = JSON.parse(raw)) } catch { return json(res, 400, { error: "bad json" }) }
  if (!/^\d{8,15}$/.test(String(to)) || typeof text !== "string" || !text.trim()) return json(res, 400, { error: "to must be 8-15 digits, text non-empty" })
  if (!connected) return json(res, 503, { error: "whatsapp not connected" })
  try {
    const [hit] = await sock.onWhatsApp(`${to}@s.whatsapp.net`)
    if (!hit?.exists) return json(res, 404, { error: "number is not on WhatsApp" })
    await sock.sendMessage(hit.jid, { text: text.slice(0, 4000) })
    json(res, 200, { ok: true })
  } catch (e) {
    console.error("send failed:", e?.message)
    json(res, 502, { error: "send failed" })
  }
}).listen(PORT, "127.0.0.1", () => console.log(`bridge on http://127.0.0.1:${PORT}`)) // localhost only: the backend is the sole caller

connect()
