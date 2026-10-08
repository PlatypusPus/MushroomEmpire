import { useNavigate } from "react-router"

import { useReplayData } from "@/api/hooks"
import { AlertFeed } from "@/components/alert-feed"
import { AppShell } from "@/components/app-shell"
import { useReplayStore } from "@/state/replayStore"

export default function Alerts() {
  const { feed, names, now, error } = useReplayData()
  const select = useReplayStore((s) => s.select)
  const navigate = useNavigate()
  return (
    <AppShell>
      <div className="flex flex-col gap-4 px-4 py-4 md:py-6 lg:px-6">
        {error && <div className="rounded-md border border-destructive p-3 text-sm text-destructive">Backend error: {String(error)}</div>}
        <AlertFeed
          feed={feed}
          names={names}
          now={now}
          onPick={(id) => {
            select(id)
            useReplayStore.getState().setMode("replay") // the alert comes from the replay, so open the replay map
            navigate("/dashboard") // open the place on the map
          }}
        />
      </div>
    </AppShell>
  )
}
