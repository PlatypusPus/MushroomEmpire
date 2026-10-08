import * as React from "react"
import { SendIcon } from "lucide-react"
import { toast } from "sonner"

import type { AssistantResult, ChatMessage } from "@/api/client"
import { streamAssistant } from "@/api/client"
import { useReplay } from "@/api/hooks"
import { useReplayStore } from "@/state/replayStore"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerViewport,
} from "@/components/ui/message-scroller"
import { cn } from "cn"

const GREETING: ChatMessage = {
  role: "assistant",
  content:
    "Grounded in live zone data. Name a place each time, e.g. “What is the status at Fort Lauderdale?” or “Why is Fort Lauderdale at risk?”",
}

const EXAMPLES = [
  "What is the status at Fort Lauderdale?",
  "Why is Fort Lauderdale at risk?",
]

export function ChatPanel() {
  const [messages, setMessages] = React.useState<ChatMessage[]>([GREETING])
  const [metas, setMetas] = React.useState<(AssistantResult | undefined)[]>([undefined])
  const [input, setInput] = React.useState("")
  const [streaming, setStreaming] = React.useState(false)
  const [model, setModel] = React.useState("")
  const [source, setSource] = React.useState("")
  const [status, setStatus] = React.useState("")
  const { eventId, tick, weights } = useReplayStore()
  const replay = useReplay(eventId, 3)
  const issueTs = replay.data?.ticks[tick]
  const abortRef = React.useRef<AbortController | null>(null)

  React.useEffect(() => () => abortRef.current?.abort(), [])

  async function send(e?: React.FormEvent) {
    e?.preventDefault()
    const content = input.trim()
    if (!content || streaming) return
    const next = [...messages, { role: "user", content } as ChatMessage]
    // Empty assistant placeholder fills in live as tokens arrive.
    setMessages([...next, { role: "assistant", content: "" }])
    setMetas((m) => [...m, undefined])
    setInput("")
    setStreaming(true)
    setStatus("loading zone data")
    const controller = new AbortController()
    abortRef.current = controller
    try {
      // Name the place in the question; share the dashboard's current
      // event/tick/weights so the answer reuses the computed tick cache
      // and matches the ranking on screen.
      const res = await streamAssistant(content, (token) => {
        setMessages((m) => {
          const copy = [...m]
          copy[copy.length - 1] = {
            ...copy[copy.length - 1],
            content: copy[copy.length - 1].content + token,
          }
          return copy
        })
      }, { signal: controller.signal, event_id: eventId, issue_ts: issueTs, weights, onStatus: setStatus })
      setMetas((m) => {
        const copy = [...m]
        copy[copy.length - 1] = res
        return copy
      })
      if (res.model) setModel(res.model.replace("ollama/", ""))
      if (res.source) setSource(res.source)
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        toast.error("Assistant unavailable", {
          description: err instanceof Error ? err.message : "The model did not answer.",
        })
        // Drop the empty placeholder so no blank bubble lingers.
        setMessages((m) => (m[m.length - 1]?.content === "" ? m.slice(0, -1) : m))
        setMetas((m) => (messages[m.length - 1]?.content === "" ? m.slice(0, -1) : m))
      }
    } finally {
      setStreaming(false)
      setStatus("")
    }
  }

  function askExample(q: string) {
    if (streaming) return
    setInput(q)
  }

  const waiting =
    streaming && messages[messages.length - 1]?.content === ""

  return (
    <Card className="flex h-[70dvh] flex-col">
      <CardHeader>
        <CardTitle>Assistant</CardTitle>
        <CardDescription>
          Grounded in zone rank, severity and drivers{model ? ` · ${model}` : ""}
          {source ? ` · ${source === "llm" ? "AI, number-checked" : "template"}` : ""}.
        </CardDescription>
        <CardAction>
          <Badge variant="outline">Grounded · zone data</Badge>
        </CardAction>
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col gap-3">
        <MessageScroller className="min-h-0 flex-1 rounded-lg border bg-muted/30">
          <MessageScrollerViewport className="p-4">
            <MessageScrollerContent>
              {messages
                .map((m, i) => ({ m, i }))
                .filter(({ m }) => m.content !== "")
                .map(({ m, i }) => {
                  const meta = metas[i]
                  return (
                    <MessageScrollerItem key={i} className="flex flex-col">
                      <div
                        className={cn(
                          "max-w-[80%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap",
                          m.role === "user"
                            ? "ml-auto bg-primary text-primary-foreground"
                            : "mr-auto bg-muted text-foreground"
                        )}
                      >
                        {m.content}
                      </div>
                      {m.role === "assistant" && meta && i > 0 && (
                        <div className="mr-auto mt-1 text-[11px] text-muted-foreground">
                          {meta.source === "llm" ? "AI · number-checked" : "template"}
                          {meta.intent ? ` · ${meta.intent}` : ""}
                        </div>
                      )}
                    </MessageScrollerItem>
                  )
                })}
              {waiting && (
                <MessageScrollerItem className="flex">
                  <div className="mr-auto animate-pulse rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground">
                    {status || "Checking zone data"}…
                  </div>
                </MessageScrollerItem>
              )}
            </MessageScrollerContent>
          </MessageScrollerViewport>
          <MessageScrollerButton />
        </MessageScroller>
        {messages.length <= 1 && (
          <div className="flex flex-wrap gap-2">
            {EXAMPLES.map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => askExample(q)}
                className="rounded-full border px-3 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                {q}
              </button>
            ))}
          </div>
        )}
        <form onSubmit={send} className="flex gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Name a place: status at …? Why is … at risk?"
            disabled={streaming}
          />
          <Button type="submit" disabled={!input.trim() || streaming}>
            <SendIcon />
            <span className="sr-only">Send</span>
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
