import { Component, type ErrorInfo, type ReactNode } from "react"

type Props = { children: ReactNode; resetKey: string }
type State = { failed: boolean; resetKey: string }

/** Un fallo de render no deja la pantalla en blanco ni muestra detalles internos. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { failed: false, resetKey: this.props.resetKey }

  static getDerivedStateFromError(): Partial<State> {
    return { failed: true }
  }

  static getDerivedStateFromProps(props: Props, state: State): Partial<State> | null {
    // Navegar a otra ruta permite recuperarse sin recargar.
    return props.resetKey !== state.resetKey ? { failed: false, resetKey: props.resetKey } : null
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Fallo de render", error.name, info.componentStack)
  }

  render() {
    if (this.state.failed) {
      return (
        <div className="panel panel-error" role="alert">
          <h1 className="panel-title">Esta pantalla no se pudo mostrar</h1>
          <p>Ninguna acción se ejecutó por este error. Usa la navegación para continuar o recarga la página.</p>
        </div>
      )
    }
    return this.props.children
  }
}
