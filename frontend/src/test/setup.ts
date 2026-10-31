import "@testing-library/jest-dom/vitest"
import { cleanup } from "@testing-library/react"
import { setupServer } from "msw/node"
import { afterAll, afterEach, beforeAll } from "vitest"
import { createHandlers } from "../mocks/handlers"

export const server = setupServer(...createHandlers())

// jsdom no implementa <dialog>.
HTMLDialogElement.prototype.showModal = function showModal() {
  this.open = true
}
HTMLDialogElement.prototype.close = function close() {
  this.open = false
}

beforeAll(() => server.listen({ onUnhandledFrame: "error" }))
afterEach(() => {
  cleanup()
  // Cada prueba arranca con estado nuevo de los mocks.
  server.resetHandlers(...createHandlers())
})
afterAll(() => server.close())
