import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { LogIn, LogOut } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Separator } from "@/components/ui/separator"
import { api, errorMessage, formatWhen, type LoginResult, type RuTrackerSession } from "@/lib/api"

export function useRuTrackerSession() {
  return useQuery({ queryKey: ["rutracker-session"], queryFn: () => api.get<RuTrackerSession>("rutracker/session") })
}

/** Login status + test login with inline captcha, shown inside the RuTracker settings card. */
export function RuTrackerSessionPanel() {
  const qc = useQueryClient()
  const { data } = useRuTrackerSession()
  const [captchaId, setCaptchaId] = useState<string | null>(null)
  const [code, setCode] = useState("")

  const login = useMutation({
    mutationFn: (body: { captcha_id?: string; captcha_code?: string }) => api.post<LoginResult>("rutracker/login", body),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["rutracker-session"] })
      if (r.status === "captcha") {
        setCaptchaId(r.captcha_id)
        setCode("")
        toast.warning("RuTracker asks for a captcha")
      } else {
        setCaptchaId(null)
        toast.success(`Logged in as ${r.username}`)
      }
    },
    onError: (e) => {
      qc.invalidateQueries({ queryKey: ["rutracker-session"] })
      setCaptchaId(null)
      toast.error(errorMessage(e))
    },
  })
  const logout = useMutation({
    mutationFn: () => api.post("rutracker/logout"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["rutracker-session"] })
      toast.success("Session cleared")
    },
  })

  return (
    <div className="grid gap-3">
      <Separator />
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium">Session</span>
        {data?.has_session && data.username ? (
          <>
            <Badge>logged in as {data.username}</Badge>
            <span className="text-muted-foreground">since {formatWhen(data.logged_in_at)}</span>
          </>
        ) : (
          <Badge variant="outline">not logged in</Badge>
        )}
      </div>
      {data?.last_error && (
        <p className="text-destructive text-sm">
          Last error ({formatWhen(data.last_error_at)}): {data.last_error}
        </p>
      )}
      {captchaId && (
        <div className="grid gap-2 rounded-md border p-3">
          <p className="text-sm">Enter the characters from the image:</p>
          <img src={`api/rutracker/captcha/${captchaId}`} alt="captcha" className="h-16 w-fit rounded bg-white" />
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              login.mutate({ captcha_id: captchaId, captcha_code: code })
            }}
          >
            <Input className="max-w-40" autoFocus value={code} onChange={(e) => setCode(e.target.value)} />
            <Button type="submit" disabled={!code || login.isPending}>
              Submit
            </Button>
          </form>
        </div>
      )}
      <div className="flex gap-2">
        <Button
          variant="outline"
          disabled={!data?.configured || login.isPending}
          title={data?.configured ? undefined : "Save username and password first"}
          onClick={() => login.mutate({})}
        >
          <LogIn /> {login.isPending ? "Logging in…" : "Test login"}
        </Button>
        {data?.has_session && (
          <Button variant="ghost" disabled={logout.isPending} onClick={() => logout.mutate()}>
            <LogOut /> Log out
          </Button>
        )}
      </div>
    </div>
  )
}

/** Tests the URL currently in the form (saved or not). */
export function FlareSolverrTest({ pending }: { pending: Record<string, string> }) {
  const test = useMutation({
    mutationFn: () => api.post<{ status: string }>("flaresolverr/test", { url: pending["flaresolverr.url"] || null }),
    onSuccess: (r) => toast.success(`FlareSolverr reachable (${r.status})`),
    onError: (e) => toast.error(errorMessage(e)),
  })
  return (
    <div>
      <Button variant="outline" disabled={test.isPending} onClick={() => test.mutate()}>
        {test.isPending ? "Testing…" : "Test connection"}
      </Button>
    </div>
  )
}

/** Tests the URL / API key currently in the form; an untouched API key uses the saved one. */
export function ArrConnectionTests({ pending }: { pending: Record<string, string> }) {
  const test = useMutation({
    mutationFn: (app: "sonarr" | "radarr") =>
      api.post<{ app: string; version: string }>(`arr/${app}/test`, {
        url: pending[`${app}.url`] || null,
        api_key: pending[`${app}.api_key`] || null,
      }),
    onSuccess: (r) => toast.success(`${r.app} reachable (version ${r.version})`),
    onError: (e) => toast.error(errorMessage(e)),
  })
  return (
    <div className="flex gap-2">
      {(["sonarr", "radarr"] as const).map((app) => (
        <Button key={app} variant="outline" disabled={test.isPending} onClick={() => test.mutate(app)}>
          Test {app === "sonarr" ? "Sonarr" : "Radarr"}
        </Button>
      ))}
    </div>
  )
}

export function QbittorrentTest({ pending }: { pending: Record<string, string> }) {
  const test = useMutation({
    mutationFn: () =>
      api.post<{ app: string; version: string }>("arr/qbittorrent/test", {
        url: pending["qbittorrent.url"] || null,
        username: pending["qbittorrent.username"] ?? null,
        password: pending["qbittorrent.password"] || null,
      }),
    onSuccess: (r) => toast.success(`${r.app} reachable (version ${r.version})`),
    onError: (e) => toast.error(errorMessage(e)),
  })
  return (
    <Button variant="outline" disabled={test.isPending} onClick={() => test.mutate()}>
      Test qBittorrent
    </Button>
  )
}
