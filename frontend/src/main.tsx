import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { BrowserRouter } from "react-router-dom"
import { Providers } from "./app/providers"
import { AppRoutes } from "./app/routes"
import { usesExampleData } from "./components/ExampleBanner"
import "./styles/tokens.css"
import "./styles/app.css"

async function start() {
  // `import.meta.env.DEV` es falso en build: este import desaparece de la distribución.
  if (import.meta.env.DEV && usesExampleData()) {
    const { worker } = await import("./mocks/browser")
    await worker.start({ onUnhandledFrame: "bypass" })
  }
  createRoot(document.getElementById("root") as HTMLElement).render(
    <StrictMode>
      <BrowserRouter>
        <Providers>
          <AppRoutes />
        </Providers>
      </BrowserRouter>
    </StrictMode>,
  )
}

void start()
