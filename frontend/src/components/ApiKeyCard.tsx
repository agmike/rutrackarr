import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Copy, Eye, EyeOff, RefreshCw } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { api, type ApiKeyView } from "@/lib/api"

export function ApiKeyCard() {
  const qc = useQueryClient()
  const [shown, setShown] = useState(false)
  const { data } = useQuery({ queryKey: ["api-key"], queryFn: () => api.get<ApiKeyView>("settings/api-key") })
  const regen = useMutation({
    mutationFn: () => api.post<ApiKeyView>("settings/api-key/regenerate"),
    onSuccess: (next) => {
      qc.setQueryData(["api-key"], next)
      toast.success("New API key generated — update the indexer and the download client in Sonarr and Radarr")
    },
    onError: (e) => toast.error(`Could not regenerate: ${e.message}`),
  })
  const copy = async () => {
    if (!data) return
    await navigator.clipboard.writeText(data.api_key)
    toast.success("API key copied")
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          API key {data?.pinned && <Badge variant="secondary">set by environment</Badge>}
        </CardTitle>
        <CardDescription className="grid gap-1">
          <span>
            Sonarr and Radarr use this one key in two places: the RuTrackarr <b>Torznab</b> indexer (URL{" "}
            <code>{new URL("torznab", document.baseURI).href}</code>, API Path <code>/api</code>), and the RuTrackarr{" "}
            <b>qBittorrent</b> download client (URL base <code>{new URL("qbit", document.baseURI).pathname}</code>, key in its
            API key field, username empty). The companion tracks script uses it too.
          </span>
          <span>
            Use the address Sonarr/Radarr reach RuTrackarr on directly (e.g.{" "}
            <code>http://rutrackarr:8787{new URL("torznab", document.baseURI).pathname}</code>), not one behind a login
            page.
          </span>
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-wrap gap-2">
        <Input readOnly className="max-w-sm font-mono" type={shown ? "text" : "password"} value={data?.api_key ?? ""} />
        <Button variant="outline" size="icon" aria-label={shown ? "Hide" : "Show"} onClick={() => setShown((s) => !s)}>
          {shown ? <EyeOff /> : <Eye />}
        </Button>
        <Button variant="outline" size="icon" aria-label="Copy" onClick={copy}>
          <Copy />
        </Button>
        {!data?.pinned && (
          <Button
            variant="outline"
            disabled={regen.isPending}
            onClick={() => {
              if (
                confirm(
                  "Generate a new API key? Sonarr and Radarr will stop working with RuTrackarr until you update it there — in the indexer and in the download client (and the companion tracks script).",
                )
              )
                regen.mutate()
            }}
          >
            <RefreshCw /> Regenerate
          </Button>
        )}
      </CardContent>
    </Card>
  )
}
