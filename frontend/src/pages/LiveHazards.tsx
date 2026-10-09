import { AppShell } from "@/components/app-shell"
import { HazardArticles } from "@/components/hazard-articles"
import { LiveHazard } from "@/components/live-hazard"

export default function LiveHazards() {
  return (
    <AppShell>
      {/* Both cards are built to fill and clip inside the dashboard's fixed-height layout. Here the page scrolls instead, so each
          wrapper keeps its card at natural height: without shrink-0 the column squeezed the articles card and hid half the articles. */}
      <div className="flex flex-col gap-4 px-4 py-4 md:py-6 lg:px-6">
        <div className="shrink-0"><LiveHazard /></div>
        <div className="shrink-0"><HazardArticles /></div>
      </div>
    </AppShell>
  )
}
