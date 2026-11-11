import { Activity, BookmarkCheck, Download, ListTree, PanelLeftClose, PanelLeftOpen, Search, Settings, SlidersHorizontal } from "lucide-react"
import { useEffect, useState } from "react"
import { NavLink, Outlet, useLocation } from "react-router"
import { useQuery } from "@tanstack/react-query"
import { Toaster } from "sonner"
import { AlertBanner } from "@/components/AlertBanner"
import { Separator } from "@/components/ui/separator"
import { api, type SystemStatus } from "@/lib/api"
import { cn } from "@/lib/utils"

const nav = [
  { to: "/", label: "Status", icon: Activity, end: true },
  { to: "/downloads", label: "Downloads", icon: Download, end: false },
  { to: "/search", label: "Search", icon: Search, end: false },
  { to: "/tracked", label: "Tracked", icon: BookmarkCheck, end: false },
  { to: "/queries", label: "Queries", icon: ListTree, end: false },
  { to: "/overrides", label: "Overrides", icon: SlidersHorizontal, end: false },
  { to: "/settings", label: "Settings", icon: Settings, end: false },
]

const COLLAPSED_KEY = "rutrackarr.sidebar.collapsed"

/** Sidebar collapsed to an icon rail: the viewer's choice, else collapsed on narrow screens. */
function useCollapsed(): [boolean, () => void] {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      const saved = localStorage.getItem(COLLAPSED_KEY)
      if (saved !== null) return saved === "1"
    } catch {
      /* storage unavailable */
    }
    return window.matchMedia("(max-width: 767px)").matches
  })
  const toggle = () =>
    setCollapsed((c) => {
      try {
        localStorage.setItem(COLLAPSED_KEY, c ? "0" : "1")
      } catch {
        /* storage unavailable */
      }
      return !c
    })
  return [collapsed, toggle]
}

export default function App() {
  const [collapsed, toggle] = useCollapsed()
  const { pathname, hash } = useLocation()
  const system = useQuery({ queryKey: ["system-status"], queryFn: () => api.get<SystemStatus>("system/status"), staleTime: 300_000 }).data
  const title = nav.find((n) => (n.end ? pathname === n.to : pathname.startsWith(n.to)))?.label ?? ""
  // Scroll to #section links (e.g. from the status page) once the page has rendered.
  useEffect(() => {
    if (hash) setTimeout(() => document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: "smooth" }), 50)
  }, [hash])
  return (
    <div className="flex min-h-svh bg-background text-foreground">
      <aside
        className={cn(
          "sticky top-0 flex h-svh shrink-0 flex-col border-r bg-sidebar transition-[width] duration-150",
          collapsed ? "w-14 p-2" : "w-56 p-3",
        )}
      >
        <div className={cn("flex items-center py-3", collapsed ? "justify-center" : "justify-between px-2")}>
          {!collapsed && <span className="text-lg font-semibold tracking-tight">RuTrackarr</span>}
          <button
            type="button"
            onClick={toggle}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="inline-flex rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            {collapsed ? <PanelLeftOpen className="size-4" /> : <PanelLeftClose className="size-4" />}
          </button>
        </div>
        <Separator className="mb-2" />
        <nav className="flex flex-col gap-1">
          {nav.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              title={collapsed ? label : undefined}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2 rounded-md py-1.5 text-sm transition-colors hover:bg-accent",
                  collapsed ? "justify-center px-0" : "px-2",
                  isActive && "bg-accent font-medium",
                )
              }
            >
              <Icon className="size-4 shrink-0" />
              {!collapsed && label}
            </NavLink>
          ))}
        </nav>
        <div className={cn("mt-auto px-2 pt-3 text-xs text-muted-foreground", collapsed && "hidden")}>
          {system && (
            <>
              v{system.version}
              {system.commit && <span className="font-mono"> · {system.commit.slice(0, 7)}</span>}
              {" · "}
            </>
          )}
          <a href={system?.repository ?? "https://github.com/agmike/rutrackarr"} target="_blank" rel="noreferrer" className="underline-offset-2 hover:underline">
            source
          </a>
        </div>
      </aside>
      <main className="min-w-0 flex-1 p-4 md:p-6">
        <h1 className="mb-4 text-2xl font-semibold tracking-tight">{title}</h1>
        <AlertBanner />
        <Outlet />
      </main>
      <Toaster theme="dark" richColors position="bottom-right" />
    </div>
  )
}
