import { Activity, Search, Settings } from "lucide-react"
import { type ReactNode, useState } from "react"
import { Separator } from "@/components/ui/separator"
import { cn } from "@/lib/utils"
import { Placeholder } from "@/pages/Placeholder"
import { StatusPage } from "@/pages/StatusPage"

type Page = { id: string; label: string; icon: ReactNode; render: () => ReactNode }

const pages: Page[] = [
  { id: "status", label: "Status", icon: <Activity className="size-4" />, render: () => <StatusPage /> },
  {
    id: "search",
    label: "Search",
    icon: <Search className="size-4" />,
    render: () => <Placeholder title="Search" text="Raw RuTracker search — coming in M1." />,
  },
  {
    id: "settings",
    label: "Settings",
    icon: <Settings className="size-4" />,
    render: () => <Placeholder title="Settings" text="RuTracker login, FlareSolverr, API keys — coming in M1." />,
  },
]

export default function App() {
  const [current, setCurrent] = useState(pages[0].id)
  const page = pages.find((p) => p.id === current) ?? pages[0]
  return (
    <div className="flex min-h-svh bg-background text-foreground">
      <aside className="flex w-56 shrink-0 flex-col border-r bg-sidebar p-3">
        <div className="px-2 py-3 text-lg font-semibold tracking-tight">rutrackarr</div>
        <Separator className="mb-2" />
        <nav className="flex flex-col gap-1">
          {pages.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => setCurrent(p.id)}
              className={cn(
                "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-accent",
                p.id === current && "bg-accent font-medium",
              )}
            >
              {p.icon}
              {p.label}
            </button>
          ))}
        </nav>
      </aside>
      <main className="flex-1 p-6">
        <h1 className="mb-4 text-2xl font-semibold tracking-tight">{page.label}</h1>
        {page.render()}
      </main>
    </div>
  )
}
