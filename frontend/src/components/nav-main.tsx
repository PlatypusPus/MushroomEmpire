import { Link, useLocation } from "react-router"
import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"

export interface NavItem {
  title: string
  url: string
  icon?: React.ReactNode
  badge?: React.ReactNode // live count or level shown at the right of the item
  tour?: string // data-tour key the guided tour spotlights
}

export function NavMain({ label, items }: { label?: string; items: NavItem[] }) {
  const { pathname } = useLocation()
  return (
    <SidebarGroup>
      {label && <SidebarGroupLabel>{label}</SidebarGroupLabel>}
      <SidebarGroupContent className="flex flex-col gap-2">
        <SidebarMenu>
          {items.map((item) => (
            <SidebarMenuItem key={item.title}>
              <SidebarMenuButton tooltip={item.title} isActive={pathname === item.url} render={<Link to={item.url} />} data-tour={item.tour}>
                {item.icon}
                <span>{item.title}</span>
              </SidebarMenuButton>
              {item.badge != null && <SidebarMenuBadge>{item.badge}</SidebarMenuBadge>}
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  )
}
