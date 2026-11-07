import { Activity, BookmarkCheck, ListTree, Search, Settings, SlidersHorizontal } from "lucide-react"
import { useEffect } from "react"
import { NavLink, Outlet, useLocation } from "react-router"
import { Toaster } from "sonner"
import { AlertBanner } from "@/components/AlertBanner"
import { Separator } from "@/components/ui/separator"
import { cn } from "@/lib/utils"

const nav = [
  { to: "/", label: "Status", icon: Activity, end: true },
  { to: "/search", label: "Search", icon: Search, end: false },
  { to: "/tracked", label: "Tracked", icon: BookmarkCheck, end: false },
  { to: "/queries", label: "Queries", icon: ListTree, end: false },
  { to: "/overrides", label: "Overrides", icon: SlidersHorizontal, end: false },
  { to: "/settings", label: "Settings", icon: Settings, end: false },
]

export default function App() {
  const { pathname, hash } = useLocation()
  const title = nav.find((n) => (n.end ? pathname === n.to : pathname.startsWith(n.to)))?.label ?? ""
  // Scroll to #section links (e.g. from the status page) once the page has rendered.
  useEffect(() => {
    if (hash) setTimeout(() => document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: "smooth" }), 50)
  }, [hash])
  return (
    <div className="flex min-h-svh bg-background text-foreground">
      <aside className="sticky top-0 flex h-svh w-56 shrink-0 flex-col border-r bg-sidebar p-3">
        <div className="px-2 py-3 text-lg font-semibold tracking-tight">RuTrackarr</div>
        <Separator className="mb-2" />
        <nav className="flex flex-col gap-1">
          {nav.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-accent",
                  isActive && "bg-accent font-medium",
                )
              }
            >
              <Icon className="size-4" />
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="flex-1 p-6">
        <h1 className="mb-4 text-2xl font-semibold tracking-tight">{title}</h1>
        <AlertBanner />
        <Outlet />
      </main>
      <Toaster theme="dark" richColors position="bottom-right" />
    </div>
  )
}
