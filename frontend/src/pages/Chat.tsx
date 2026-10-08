import { AppShell } from "@/components/app-shell"
import { ChatPanel } from "@/components/chat-panel"

export default function Chat() {
  return (
    <AppShell>
      {/* Single padded column: the panel height below exactly fills the
          viewport remainder (site header + this padding), so the message
          list is the only scroller and the input stays pinned at the bottom. */}
      <div className="flex min-h-0 flex-1 flex-col px-4 py-4 lg:px-6">
        <ChatPanel className="h-[calc(100dvh-var(--header-height)-2rem)]" />
      </div>
    </AppShell>
  )
}
