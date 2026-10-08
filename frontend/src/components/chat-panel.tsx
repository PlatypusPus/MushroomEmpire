import * as React from "react"
import { SendIcon } from "lucide-react"
import { toast } from "sonner"

import type { ChatMessage } from "@/api/client"
import { streamChat } from "@/api/client"
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
    "KADAL assistant, Ask away!"
}

export function ChatPanel() {
  const [messages, setMessages] = React.useState<ChatMessage[]>([GREETING])
  const [input, setInput] = React.useState("")
  const [streaming, setStreaming] = React.useState(false)
  const [model, setModel] = React.useState("")
  const abortRef = React.useRef<AbortController | null>(null)

  React.useEffect(() => () => abortRef.current?.abort(), [])

  async function send(e?: React.FormEvent) {
    e?.preventDefault()
    const content = input.trim()
    if (!content || streaming) return
    const next = [...messages, { role: "user", content } as ChatMessage]
    // Empty assistant placeholder fills in live as tokens arrive.
    setMessages([...next, { role: "assistant", content: "" }])
    setInput("")
    setStreaming(true)
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const name = await streamChat(next, (token) => {
        setMessages((m) => {
          const copy = [...m]
          copy[copy.length - 1] = {
            ...copy[copy.length - 1],
            content: copy[copy.length - 1].content + token,
          }
          return copy
        })
      }, { signal: controller.signal })
      setModel(name)
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        toast.error("Chat unavailable", {
          description: err instanceof Error ? err.message : "The model did not answer.",
        })
        // Drop the empty placeholder so no blank bubble lingers.
        setMessages((m) => (m[m.length - 1]?.content === "" ? m.slice(0, -1) : m))
      }
    } finally {
      setStreaming(false)
    }
  }

  const waiting =
    streaming && messages[messages.length - 1]?.content === ""

  return (
    <Card className="flex h-[70dvh] flex-col">
      <CardHeader>
        <CardTitle>Assistant</CardTitle>
        <CardDescription>
          Simple chat with the local model{model ? ` · ${model}` : ""}.
        </CardDescription>
        <CardAction>
          <Badge variant="outline">Experimental · ungrounded</Badge>
        </CardAction>
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col gap-3">
        <MessageScroller className="min-h-0 flex-1 rounded-lg border bg-muted/30">
          <MessageScrollerViewport className="p-4">
            <MessageScrollerContent>
              {messages
                .filter((m) => m.content !== "")
                .map((m, i) => (
                <MessageScrollerItem key={i} className="flex">
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
                </MessageScrollerItem>
              ))}
              {waiting && (
                <MessageScrollerItem className="flex">
                  <div className="mr-auto animate-pulse rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground">
                    Thinking…
                  </div>
                </MessageScrollerItem>
              )}
            </MessageScrollerContent>
          </MessageScrollerViewport>
          <MessageScrollerButton />
        </MessageScroller>
        <form onSubmit={send} className="flex gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about flood response…"
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
