import { NextResponse } from 'next/server';

const CHAT_HOST = process.env.CHAT_API_URL || process.env.NEXT_PUBLIC_CHAT_API_URL || 'https://f52c8f4e7dfc.ngrok-free.app';

export async function POST(req: Request) {
  try {
    const body = await req.json().catch(() => ({}));
    const prompt = typeof body?.prompt === 'string' ? body.prompt : '';
    if (!prompt.trim()) {
      return NextResponse.json({ detail: 'Missing prompt' }, { status: 400 });
    }

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 120_000);
    try {
      const upstream = await fetch(`${CHAT_HOST}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify({ prompt }),
        signal: controller.signal,
      });

      const text = await upstream.text();
      let json: any;
      try { json = JSON.parse(text); } catch { json = { response: text }; }

      if (!upstream.ok) {
        return NextResponse.json(json || { detail: 'Chat failed' }, { status: upstream.status });
      }
      return NextResponse.json(json);
    } finally {
      clearTimeout(timeout);
    }
  } catch (err: any) {
    const msg = err?.name === 'AbortError' ? 'Request timed out – model may be overloaded.' : (err?.message || 'Unexpected error');
    return NextResponse.json({ detail: msg }, { status: 500 });
  }
}
