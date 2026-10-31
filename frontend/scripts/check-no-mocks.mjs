// Falla el build si algo de MSW o de los datos de ejemplo llegó a la distribución.
import { readdirSync, readFileSync, statSync } from "node:fs"
import { join } from "node:path"

const FORBIDDEN = ["mockServiceWorker", "setupWorker", "mock-operator"]

function files(directory) {
  return readdirSync(directory).flatMap((name) => {
    const path = join(directory, name)
    return statSync(path).isDirectory() ? files(path) : [path]
  })
}

const found = files("dist").flatMap((path) => {
  const text = readFileSync(path, "utf-8")
  return FORBIDDEN.filter((term) => text.includes(term)).map((term) => `${path}: ${term}`)
})

if (found.length > 0) {
  console.error(`El build contiene mocks:\n${found.join("\n")}`)
  process.exit(1)
}
console.log("Build sin mocks.")
