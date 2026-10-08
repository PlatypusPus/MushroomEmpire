import * as React from "react"
import { BellRingIcon, LayoutDashboardIcon, ListOrderedIcon, MessageSquareIcon, ChartColumnIcon, RadioIcon, WavesIcon } from "lucide-react"

import { useLiveContext, useReplayData } from "@/api/hooks"
import { NavMain } from "@/components/nav-main"
import { NavUser } from "@/components/nav-user"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const { feed, now } = useReplayData()
  const live = useLiveContext()
  const fresh = feed.filter((a) => a.issue_ts === now).length

  const monitor = [
    { title: "Dashboard", url: "/dashboard", icon: <LayoutDashboardIcon /> },
    { title: "Response priority", url: "/priority", icon: <ListOrderedIcon /> },
    {
      title: "Alerts", url: "/alerts", icon: <BellRingIcon />,
      // new alerts at the current replay step, else everything fired so far
      badge: feed.length ? (fresh ? <span className="text-destructive">{fresh} new</span> : feed.length) : null,
    },
    {
      title: "Live hazards", url: "/live", icon: <RadioIcon />,
      badge: live.data ? `L${live.data.level}` : live.error ? "off" : null,
    },
  ]
  const analyse = [
    { title: "Assistant", url: "/chat", icon: <MessageSquareIcon /> },
    { title: "Model validation", url: "/validation", icon: <ChartColumnIcon /> },
  ]

  return (
    <Sidebar collapsible="offcanvas" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton className="data-[slot=sidebar-menu-button]:p-1.5!" render={<a href="/" />}>
              <WavesIcon className="size-5!" />
              <span className="text-base font-semibold">KADAL</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <NavMain label="Monitor" items={monitor} />
        <NavMain label="Analyse" items={analyse} />
        <p className="mt-auto px-4 pb-2 text-xs text-muted-foreground">
          We only suggest, we never send anyone. Live warnings are separate and are not used by our flood forecast.
        </p>
      </SidebarContent>
      <SidebarFooter>
        <NavUser />
      </SidebarFooter>
    </Sidebar>
  )
}
