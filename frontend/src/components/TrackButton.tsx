import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { BookmarkCheck, BookmarkPlus } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { api, errorMessage, type TrackedView } from "@/lib/api"

type Topic = { topic_id: number; title: string; forum: string; forum_id: number | null; size: number; seeders: number }

/** Track a search result: RuTrackarr downloads it (tracking category) and follows its updates. */
export function TrackButton({ topic, compact = false }: { topic: Topic; compact?: boolean }) {
  const qc = useQueryClient()
  const tracked = useQuery({ queryKey: ["tracked"], queryFn: () => api.get<TrackedView>("tracked"), staleTime: 30_000 })
  const isTracked = tracked.data?.items.some((t) => t.topic_id === topic.topic_id && t.state === "active")
  const track = useMutation({
    mutationFn: () =>
      api.post("tracked", {
        topic: String(topic.topic_id),
        title: topic.title,
        forum: topic.forum,
        forum_id: topic.forum_id,
        size: topic.size,
        seeders: topic.seeders,
      }),
    onSuccess: () => {
      toast.success("Tracking — added to qBittorrent")
      qc.invalidateQueries({ queryKey: ["tracked"] })
    },
    onError: (e) => toast.error(errorMessage(e)),
  })
  if (isTracked)
    return (
      <span className="inline-flex shrink-0 text-emerald-600 dark:text-emerald-400" title="Tracked">
        <BookmarkCheck className={compact ? "size-3.5" : "size-4"} />
      </span>
    )
  if (compact)
    // Sized and spaced like the bare link icons next to it.
    return (
      <button
        type="button"
        className="inline-flex shrink-0 text-muted-foreground hover:text-foreground disabled:opacity-50"
        title="Track: download it and follow updates"
        aria-label="Track"
        disabled={track.isPending}
        onClick={() => track.mutate()}
      >
        <BookmarkPlus className="size-3.5" />
      </button>
    )
  return (
    <Button size="sm" variant="ghost" title="Track: download it and follow updates" disabled={track.isPending} onClick={() => track.mutate()}>
      <BookmarkPlus />
    </Button>
  )
}
