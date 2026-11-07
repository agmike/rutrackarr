/** A small labelled number, for rows of stats inside a card. */
export function StatTile({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div className="grid min-w-0 gap-0.5 rounded-md border bg-muted/30 px-3 py-2" title={hint}>
      <span className="truncate text-xs text-muted-foreground">{label}</span>
      <span className="truncate text-lg font-semibold tabular-nums">{value}</span>
    </div>
  )
}
