export function usesExampleData(): boolean {
  return import.meta.env.DEV && import.meta.env.VITE_USE_MOCKS === "true"
}

/** Marca persistente: ningún dato simulado se presenta como una ejecución real. */
export function ExampleBanner() {
  if (!usesExampleData()) {
    return null
  }
  return (
    <span className="example-banner" role="status">
      DATOS DE EJEMPLO
    </span>
  )
}
