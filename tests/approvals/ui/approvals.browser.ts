import { expect, test } from "@playwright/test"
import { fileURLToPath } from "node:url"
import type { ApprovalDetail } from "../../../frontend/src/features/approvals/types"

const axeFile = fileURLToPath(new URL("./node_modules/axe-core/axe.min.js", import.meta.url))
const fixture: ApprovalDetail = {
  approval_id: "approval-fixture", request_id: "request-fixture", status: "PENDING", row_version: 1,
  expires_at: "2099-10-31T12:05:00Z", created_at: "2026-10-31T12:00:00Z", agent_id: "demo-agent",
  principal_id: "demo-agent-principal", policy_id: "demo-policy", policy_version: 1,
  request_digest: "a".repeat(64), risk: "HIGH", request_state: "PENDING_APPROVAL", receipt: null,
  snapshot: { principal_id: "demo-agent-principal", environment_id: "protected-fixture", resource_version: 1,
    call: { request_id: "request-fixture", agent_id: "demo-agent", tool: "email.send", operation: "send", resource_id: "mailbox:demo-outbox",
      parameters: { to: "reviewer@example.test", subject: "Correo sintético de prueba", body: "Datos ficticios para verificar layout y autorización humana." } } },
}

for (const width of [360, 768, 1280]) {
  test(`Persona 3 keyboard, layout and full axe at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 })
    let item = structuredClone(fixture)
    const decisions: unknown[] = []
    await page.route("**/api/v1/**", async (route) => {
      const path = new URL(route.request().url()).pathname
      if (path === "/api/v1/auth/me") return route.fulfill({ json: { principal_id: "human-approver", username: "reviewer", kind: "human", roles: ["viewer", "approver"], csrf_token: "fixture-csrf" } })
      if (path.endsWith("/approve")) {
        decisions.push(route.request().postDataJSON())
        expect(route.request().headers()["x-csrf-token"]).toBe("fixture-csrf")
        item = { ...item, status: "CONSUMED", row_version: 2, request_state: "SUCCEEDED" }
        return route.fulfill({ json: item })
      }
      if (path === "/api/v1/approvals") return route.fulfill({ json: { items: [item], next_cursor: null } })
      if (path === "/api/v1/approvals/approval-fixture") return route.fulfill({ json: item })
      return route.fulfill({ status: 404, json: { error: { code: "NOT_FOUND" } } })
    })
    await page.goto("/")
    await expect(page.getByText(/DATOS DE PRUEBA/)).toBeVisible()
    await page.getByRole("button", { name: /Ver solicitud.*request-fixture/ }).focus()
    await page.keyboard.press("Enter")
    await expect(page.getByText("Parámetros recibidos")).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.addScriptTag({ path: axeFile })
    const violations = await page.evaluate(async () => {
      const result = await (window as unknown as { axe: { run: () => Promise<{ violations: { id: string; impact: string; nodes: { target: unknown }[] }[] }> } }).axe.run()
      return result.violations.map((issue) => ({ id: issue.id, impact: issue.impact, nodes: issue.nodes.map((node) => node.target) }))
    })
    expect(violations).toEqual([])
    await page.screenshot({ path: `.artifacts/persona-3-${width}.png`, fullPage: true })
    await page.getByRole("button", { name: "Aprobar", exact: true }).click()
    const dialog = page.getByRole("dialog", { name: "Aprobar" })
    const reason = dialog.getByRole("textbox", { name: "Motivo de la decisión" })
    await expect(reason).toBeFocused()
    await page.keyboard.press("Shift+Tab")
    await expect(dialog.getByRole("button", { name: "Volver al detalle" })).toBeFocused()
    await page.keyboard.press("Tab")
    await expect(reason).toBeFocused()
    await reason.fill("Solicitud exacta revisada en prueba de Persona 3")
    const dialogViolations = await page.evaluate(async () => {
      const result = await (window as unknown as { axe: { run: () => Promise<{ violations: { id: string }[] }> } }).axe.run()
      return result.violations.map((issue) => issue.id)
    })
    expect(dialogViolations).toEqual([])
    await page.screenshot({ path: `.artifacts/persona-3-dialog-${width}.png`, fullPage: false })
    await dialog.getByRole("button", { name: "Confirmar decisión" }).click()
    await expect(page.getByText(/Respuesta confirmada/)).toHaveText("Respuesta confirmada: Consumida. Ejecución: SUCCEEDED.")
    expect(decisions).toEqual([{ expected_version: 1, reason: "Solicitud exacta revisada en prueba de Persona 3" }])
  })
}
