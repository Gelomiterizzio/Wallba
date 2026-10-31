import { useEffect, useRef, useState } from "react"
import { NavLink, Outlet, useLocation } from "react-router-dom"
import { ErrorBoundary } from "../components/ErrorBoundary"
import { ExampleBanner } from "../components/ExampleBanner"
import { useSession } from "./session"

const NAVIGATION = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/agents", label: "Agentes" },
  { to: "/policies", label: "Políticas" },
  { to: "/approvals", label: "Aprobaciones" },
  { to: "/audit", label: "Auditoría" },
  { to: "/playground", label: "Playground" },
  { to: "/matrix", label: "Matriz de ataques" },
  { to: "/protection", label: "Protección" },
  { to: "/alerts", label: "Alertas" },
]

export function AppShell() {
  const { session, logout } = useSession()
  const { pathname } = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const [theme, setTheme] = useState<"dark" | "light">(() =>
    window.localStorage.getItem("wallba-theme") === "light" ? "light" : "dark",
  )
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    window.localStorage.setItem("wallba-theme", theme)
  }, [theme])
  const mainRef = useRef<HTMLElement>(null)
  const previousPath = useRef(pathname)

  useEffect(() => {
    // Solo al cambiar de ruta: al cargar, el primer Tab debe llegar a "Saltar al contenido".
    if (previousPath.current !== pathname) {
      previousPath.current = pathname
      setMenuOpen(false)
      mainRef.current?.focus()
    }
  }, [pathname])

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Saltar al contenido
      </a>
      <header className="shell-header">
        <button
          type="button"
          className="button menu-button"
          aria-expanded={menuOpen}
          aria-controls="primary-nav"
          onClick={() => setMenuOpen((open) => !open)}
        >
          Menú
        </button>
        <span className="brand">WALLBA</span>
        <button
          type="button"
          className="button"
          onClick={() => setTheme((current) => (current === "dark" ? "light" : "dark"))}
        >
          {theme === "dark" ? "Usar tema claro" : "Usar tema oscuro"}
        </button>
        <span className="environment-tag">DEMO AISLADA</span>
        <ExampleBanner />
        <div className="identity">
          <span className="identity-name mono">{session?.principal_id}</span>
          <span className="identity-roles">{session?.roles.join(", ")}</span>
          <button type="button" className="button" onClick={() => void logout()}>
            Cerrar sesión
          </button>
        </div>
      </header>
      <nav id="primary-nav" className={`shell-nav${menuOpen ? " is-open" : ""}`} aria-label="Principal">
        <ul>
          {NAVIGATION.map((item) => (
            <li key={item.to}>
              <NavLink to={item.to} className="nav-link">
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <main id="main" className="shell-main" tabIndex={-1} ref={mainRef}>
        <ErrorBoundary resetKey={pathname}>
          <Outlet />
        </ErrorBoundary>
      </main>
    </div>
  )
}
