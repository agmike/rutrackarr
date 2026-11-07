import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { Input } from "@/components/ui/input"
import { api, type LibraryItem } from "@/lib/api"

/** Type to find a series (Sonarr) or film (Radarr) from the libraries. */
export function LibraryPicker({ onPick, placeholder }: { onPick: (item: LibraryItem) => void; placeholder?: string }) {
  const [text, setText] = useState("")
  const [open, setOpen] = useState(false)
  const q = useQuery({
    queryKey: ["library", text],
    queryFn: () => api.get<{ items: LibraryItem[] }>(`sandbox/library?q=${encodeURIComponent(text)}`),
    enabled: open && text.trim().length >= 2,
  })
  return (
    <div className="relative">
      <Input
        value={text}
        placeholder={placeholder ?? "Find a series or film in Sonarr/Radarr…"}
        onChange={(e) => {
          setText(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {open && q.data && q.data.items.length > 0 && (
        <ul className="absolute z-10 mt-1 max-h-72 w-full overflow-auto rounded-md border bg-popover p-1 text-sm shadow-md">
          {q.data.items.map((i) => (
            <li key={`${i.kind}-${i.tvdbid ?? i.tmdbid}`}>
              <button
                type="button"
                className="flex w-full items-center gap-2 rounded px-2 py-1 text-left hover:bg-accent"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  onPick(i)
                  setText(i.title)
                  setOpen(false)
                }}
              >
                <span className="min-w-0 flex-1 truncate">{i.title}</span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {i.year ?? ""} · {i.kind === "movie" ? "film" : i.series_type === "anime" ? "anime" : "series"}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
