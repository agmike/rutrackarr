import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export function Placeholder({ title, text }: { title: string; text: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{text}</CardDescription>
      </CardHeader>
    </Card>
  )
}
