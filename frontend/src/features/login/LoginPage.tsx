import { useState, type FormEvent } from "react"
import { ApiRequestError } from "../../api/client"
import { useSession } from "../../app/session"

export function LoginPage() {
  const { login } = useSession()
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (pending) {
      return
    }
    setPending(true)
    setError(null)
    try {
      await login(username, password)
    } catch (reason) {
      // Mensaje genérico: no revela si la cuenta existe.
      setError(
        reason instanceof ApiRequestError && reason.status === 401
          ? "Usuario o contraseña incorrectos."
          : "No se pudo iniciar sesión. Inténtalo de nuevo.",
      )
      setPassword("")
    } finally {
      setPending(false)
    }
  }

  return (
    <main className="login-page">
      <form className="panel login-card" onSubmit={(event) => void submit(event)}>
        <h1>WALLBA</h1>
        <p className="meta">DEMO AISLADA · solo recursos sintéticos</p>
        <div className="field">
          <label htmlFor="username">Usuario</label>
          <input
            id="username"
            autoComplete="username"
            required
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="password">Contraseña</label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            aria-describedby={error ? "login-error" : undefined}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>
        {error ? (
          <p id="login-error" role="alert">
            {error}
          </p>
        ) : null}
        <button type="submit" className="button button-primary" disabled={pending}>
          {pending ? "Entrando…" : "Iniciar sesión"}
        </button>
      </form>
    </main>
  )
}
