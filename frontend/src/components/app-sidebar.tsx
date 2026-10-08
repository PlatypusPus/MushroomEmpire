import * as React from "react"

import { NavMain } from "@/components/nav-main"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import { LayoutDashboardIcon, MessageSquareIcon, ScaleIcon, WavesIcon } from "lucide-react"

const NAV = [
  { title: "Dashboard", url: "/", icon: <LayoutDashboardIcon /> },
  { title: "Assistant", url: "/chat", icon: <MessageSquareIcon /> },
  { title: "Model honesty", url: "/honesty", icon: <ScaleIcon /> },
]

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
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
        <NavMain items={NAV} />
      </SidebarContent>
      <SidebarFooter>
        <p className="px-2 text-xs text-muted-foreground">
          Coastal high-water intelligence, South Florida. Recommends only; never dispatches.
        </p>
      </SidebarFooter>
    </Sidebar>
  )
}
