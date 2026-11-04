import { useMutation, useQueryClient } from "@tanstack/react-query"
import { type ReactNode, useEffect, useMemo, useState } from "react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { api, fieldErrors, type SettingsView } from "@/lib/api"

export type FieldSpec = {
  key: string
  label: string
  type: "text" | "url" | "number" | "secret"
  help?: ReactNode
  placeholder?: string
}

type SecretChange = { set: string } | { clear: true }

export function SettingsSection({
  title,
  description,
  fields,
  view,
  children,
}: {
  title: string
  description?: ReactNode
  fields: FieldSpec[]
  view: SettingsView
  /** Extra controls; a function gets the values entered but not saved yet (secrets only when typed). */
  children?: ReactNode | ((pending: Record<string, string>) => ReactNode)
}) {
  const qc = useQueryClient()
  const initial = useMemo(
    () => Object.fromEntries(fields.filter((f) => f.type !== "secret").map((f) => [f.key, String(view.values[f.key] ?? "")])),
    [fields, view],
  )
  const [values, setValues] = useState<Record<string, string>>(initial)
  const [secrets, setSecrets] = useState<Record<string, SecretChange>>({})
  const [errors, setErrors] = useState<Record<string, string>>({})
  useEffect(() => setValues(initial), [initial])

  const changes = useMemo(() => {
    const out: Record<string, string | number> = {}
    for (const f of fields) {
      if (f.type === "secret") {
        const c = secrets[f.key]
        if (c && "set" in c && c.set !== "") out[f.key] = c.set
        if (c && "clear" in c) out[f.key] = ""
      } else if (values[f.key] !== initial[f.key]) {
        out[f.key] = f.type === "number" ? values[f.key] : values[f.key]
      }
    }
    return out
  }, [fields, values, secrets, initial])
  const dirty = Object.keys(changes).length > 0

  const save = useMutation({
    mutationFn: () => api.put<SettingsView>("settings", { values: changes }),
    onSuccess: (next) => {
      qc.setQueryData(["settings"], next)
      setSecrets({})
      setErrors({})
      toast.success(`${title} saved`)
    },
    onError: (err) => {
      const fe = fieldErrors(err)
      setErrors(fe)
      toast.error(Object.keys(fe).length ? "Please fix the highlighted fields" : `Saving failed: ${err.message}`)
    },
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent className="grid gap-4">
        {fields.map((f) => (
          <div key={f.key} className="grid gap-1.5">
            <div className="flex items-center gap-2">
              <Label htmlFor={f.key}>{f.label}</Label>
              {f.type === "secret" && <SecretBadge saved={view.secrets[f.key]} change={secrets[f.key]} />}
            </div>
            {f.type === "secret" ? (
              <div className="flex gap-2">
                <Input
                  id={f.key}
                  type="password"
                  autoComplete="new-password"
                  placeholder={view.secrets[f.key] ? "Leave empty to keep the saved value" : (f.placeholder ?? "")}
                  value={(secrets[f.key] && "set" in secrets[f.key] ? (secrets[f.key] as { set: string }).set : "") ?? ""}
                  onChange={(e) => setSecrets((s) => ({ ...s, [f.key]: { set: e.target.value } }))}
                  aria-invalid={!!errors[f.key]}
                />
                {view.secrets[f.key] && (
                  <Button type="button" variant="outline" onClick={() => setSecrets((s) => ({ ...s, [f.key]: { clear: true } }))}>
                    Clear
                  </Button>
                )}
              </div>
            ) : (
              <Input
                id={f.key}
                type={f.type === "number" ? "number" : f.type === "url" ? "url" : "text"}
                placeholder={f.placeholder}
                value={values[f.key] ?? ""}
                onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
                aria-invalid={!!errors[f.key]}
              />
            )}
            {errors[f.key] ? (
              <p className="text-destructive text-sm">{errors[f.key]}</p>
            ) : (
              f.help && <p className="text-muted-foreground text-sm">{f.help}</p>
            )}
          </div>
        ))}
        {typeof children === "function" ? children(pendingValues(fields, values, secrets)) : children}
      </CardContent>
      <CardFooter className="justify-end gap-2">
        <Button
          variant="ghost"
          disabled={!dirty || save.isPending}
          onClick={() => {
            setValues(initial)
            setSecrets({})
            setErrors({})
          }}
        >
          Reset
        </Button>
        <Button disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? "Saving…" : "Save"}
        </Button>
      </CardFooter>
    </Card>
  )
}

function pendingValues(
  fields: FieldSpec[],
  values: Record<string, string>,
  secrets: Record<string, SecretChange>,
): Record<string, string> {
  const out: Record<string, string> = {}
  for (const f of fields) {
    if (f.type !== "secret") out[f.key] = values[f.key] ?? ""
    else {
      const c = secrets[f.key]
      if (c && "set" in c && c.set) out[f.key] = c.set
    }
  }
  return out
}

function SecretBadge({ saved, change }: { saved: boolean; change?: SecretChange }) {
  if (change && "clear" in change) return <Badge variant="destructive">will be cleared</Badge>
  if (change && "set" in change && change.set) return <Badge variant="secondary">will be replaced</Badge>
  return saved ? <Badge variant="secondary">saved</Badge> : <Badge variant="outline">not set</Badge>
}
