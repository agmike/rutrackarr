import { useQuery } from "@tanstack/react-query"
import { ActivityCard } from "@/components/ActivityCard"
import { ConnectionsCard } from "@/components/ConnectionsCard"
import { DownloadsCard } from "@/components/DownloadsCard"
import { QueriesCard } from "@/components/QueriesCard"
import { RecentGrabsCard } from "@/components/RecentGrabsCard"
import { ServiceCard } from "@/components/ServiceCard"
import { SessionCard } from "@/components/SessionCard"
import { SetupChecklist } from "@/components/SetupChecklist"
import { TrackingCard } from "@/components/TrackingCard"
import { api, type SettingsView } from "@/lib/api"

export function StatusPage() {
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api.get<SettingsView>("settings") })
  return (
    <div className="grid max-w-5xl gap-4 md:grid-cols-2">
      <ServiceCard />
      <SessionCard />
      {settings.data && <SetupChecklist settings={settings.data} />}
      <DownloadsCard />
      <TrackingCard />
      <RecentGrabsCard />
      <ActivityCard />
      <QueriesCard />
      <ConnectionsCard />
    </div>
  )
}
