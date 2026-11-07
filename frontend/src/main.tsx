import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { createBrowserRouter, RouterProvider } from "react-router"
import "./index.css"
import App from "./App.tsx"
import { routerBasename } from "./lib/basename"
import { OverridesPage } from "./pages/OverridesPage"
import { QueriesPage } from "./pages/QueriesPage"
import { SandboxPage } from "./pages/SandboxPage"
import { SearchPage } from "./pages/SearchPage"
import { SettingsPage } from "./pages/SettingsPage"
import { StatusPage } from "./pages/StatusPage"

// Dark by default (shadcn theme variables switch on the .dark class).
document.documentElement.classList.add("dark")

const router = createBrowserRouter(
  [
    {
      path: "/",
      element: <App />,
      children: [
        { index: true, element: <StatusPage /> },
        { path: "search", element: <SearchPage /> },
        { path: "sandbox", element: <SandboxPage /> },
        { path: "queries", element: <QueriesPage /> },
        { path: "overrides", element: <OverridesPage /> },
        { path: "settings", element: <SettingsPage /> },
      ],
    },
  ],
  { basename: routerBasename() },
)

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } })

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
