import { AppShell } from "@/components/app-shell"
import { ChatPanel } from "@/components/chat-panel"

export default function Chat() {
  return (
    <AppShell>
      <div className="flex flex-1 flex-col">
        <div className="@container/main flex flex-1 flex-col gap-2">
          <div className="flex flex-col gap-4 px-4 py-4 md:gap-6 md:py-6 lg:px-6">
            <ChatPanel />
          </div>
        </div>
      </div>
    </AppShell>
  )
}
