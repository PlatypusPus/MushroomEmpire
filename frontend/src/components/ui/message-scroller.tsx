import * as React from "react"
import { ArrowDownIcon } from "lucide-react"
import { cn } from "cn"

import { Button } from "@/components/ui/button"

interface ScrollerContext {
  viewportRef: React.RefObject<HTMLDivElement | null>
  isAtEnd: boolean
  setAtEnd: (v: boolean) => void
  scrollToEnd: (behavior?: ScrollBehavior) => void
}

const MessageScrollerContext = React.createContext<ScrollerContext | null>(null)

function useMessageScroller() {
  const ctx = React.useContext(MessageScrollerContext)
  if (!ctx) throw new Error("useMessageScroller must be used within MessageScroller")
  return ctx
}

function MessageScroller({ className, ...props }: React.ComponentProps<"div">) {
  const viewportRef = React.useRef<HTMLDivElement>(null)
  const [isAtEnd, setIsAtEnd] = React.useState(true)

  const scrollToEnd = React.useCallback((behavior: ScrollBehavior = "smooth") => {
    viewportRef.current?.scrollTo({
      top: viewportRef.current.scrollHeight,
      behavior,
    })
  }, [])

  const value = React.useMemo(
    () => ({ viewportRef, isAtEnd, setAtEnd: setIsAtEnd, scrollToEnd }),
    [isAtEnd, scrollToEnd]
  )

  return (
    <MessageScrollerContext.Provider value={value}>
      <div
        data-slot="message-scroller"
        className={cn(
          "group/message-scroller relative flex size-full min-h-0 flex-col overflow-hidden",
          className
        )}
        {...props}
      />
    </MessageScrollerContext.Provider>
  )
}

function nearBottom(el: HTMLElement) {
  return el.scrollHeight - el.scrollTop - el.clientHeight < 48
}

function MessageScrollerViewport({ className, ...props }: React.ComponentProps<"div">) {
  const { viewportRef, setAtEnd } = useMessageScroller()
  return (
    <div
      ref={viewportRef}
      data-slot="message-scroller-viewport"
      onScroll={(e) => setAtEnd(nearBottom(e.currentTarget))}
      className={cn("size-full min-h-0 min-w-0 overflow-y-auto overscroll-contain", className)}
      {...props}
    />
  )
}

function MessageScrollerContent({ className, ...props }: React.ComponentProps<"div">) {
  const { viewportRef, isAtEnd, scrollToEnd } = useMessageScroller()
  const stickRef = React.useRef(true)
  stickRef.current = isAtEnd

  // Auto-stick to bottom on new content only if the user was already there.
  React.useEffect(() => {
    const viewport = viewportRef.current
    const content = viewport?.firstElementChild
    if (!viewport || !content) return
    const ro = new ResizeObserver(() => {
      if (stickRef.current) scrollToEnd("auto")
    })
    ro.observe(content)
    return () => ro.disconnect()
  }, [viewportRef, scrollToEnd])

  return (
    <div
      data-slot="message-scroller-content"
      className={cn("flex h-max min-h-full flex-col gap-4", className)}
      {...props}
    />
  )
}

function MessageScrollerItem({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="message-scroller-item"
      className={cn("min-w-0 shrink-0", className)}
      {...props}
    />
  )
}

function MessageScrollerButton({ className }: { className?: string }) {
  const { isAtEnd, scrollToEnd } = useMessageScroller()
  if (isAtEnd) return null
  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-4 flex justify-center">
      <Button
        variant="secondary"
        size="icon"
        onClick={() => scrollToEnd()}
        className={cn("pointer-events-auto rounded-full border shadow-md", className)}
      >
        <ArrowDownIcon />
        <span className="sr-only">Scroll to end</span>
      </Button>
    </div>
  )
}

export {
  MessageScroller,
  MessageScrollerViewport,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerButton,
  useMessageScroller,
}
