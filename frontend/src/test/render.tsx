import { render } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { Providers } from "../app/providers"
import { AppRoutes } from "../app/routes"

/** Monta la aplicación real (rutas, sesión, caché) contra los handlers de MSW. */
export function renderApp(route = "/dashboard") {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Providers>
        <AppRoutes />
      </Providers>
    </MemoryRouter>,
  )
}
