import { AppShell } from "@/components/app-shell"
import { HazardArticles } from "@/components/hazard-articles"
import { LiveHazard } from "@/components/live-hazard"

export default function LiveHazards() {
  return (
    <AppShell>
      <div className="flex flex-col gap-4 px-4 py-4 md:py-6 lg:px-6">
        <LiveHazard />
        <HazardArticles />
      </div>
    </AppShell>
  )
}
