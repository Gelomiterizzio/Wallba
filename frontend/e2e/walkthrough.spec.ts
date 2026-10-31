/** Recorrido en navegador real sobre DATOS DE EJEMPLO. No es evidencia de la protección real. */
import AxeBuilder from "@axe-core/playwright"
import { expect, test, type Page } from "@playwright/test"
import fixtures from "../src/mocks/fixtures.json" with { type: "json" }

const S04 = fixtures.demoRuns.S04.run_id
const S06 = fixtures.demoRuns.S06.run_id
const UNKNOWN = fixtures.demoRuns.UNKNOWN.run_id
const EVENT = fixtures.auditEvents[3].event_id

const ROUTES = [
  { path: "/dashboard", heading: "Dashboard" },
  { path: "/agents", heading: "Agentes" },
  { path: "/agents/demo-agent", heading: "Agente de demostración" },
  { path: "/policies", heading: /Polític/ },
  { path: "/approvals", heading: "Aprobaciones" },
  { path: "/audit", heading: "Auditoría" },
  { path: `/audit/${EVENT}`, heading: "Evento 4" },
  { path: "/playground", heading: "Playground" },
  { path: `/playground/${S04}`, heading: "Comparación S04" },
  { path: `/playground/${S06}`, heading: "Comparación S06" },
  { path: `/playground/${UNKNOWN}`, heading: "Comparación S08" },
  { path: "/matrix", heading: "Matriz de ataques" },
]
const VIEWPORTS = [
  { width: 360, height: 800 },
  { width: 768, height: 1024 },
  { width: 1440, height: 900 },
]

async function gotoReady(page: Page, path: string, heading: string | RegExp) {
  await page.goto(path)
  await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible()
  await expect(page.locator("[aria-busy='true']")).toHaveCount(0)
}

for (const viewport of VIEWPORTS) {
  test.describe(`${viewport.width}px`, () => {
    test.use({ viewport })

    for (const route of ROUTES) {
      test(`${route.path} es accesible, sin desborde y marcada como ejemplo`, async ({ page }, info) => {
        await gotoReady(page, route.path, route.heading)
        await expect(page.getByText("DATOS DE EJEMPLO").first()).toBeVisible()

        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
        expect(overflow, "la página no debe desplazarse en horizontal").toBeLessThanOrEqual(0)

        const results = await new AxeBuilder({ page }).analyze()
        const serious = results.violations.filter((item) => item.impact === "critical" || item.impact === "serious")
        expect(serious.map((item) => `${item.id}: ${item.nodes.map((node) => node.target).join(" | ")}`)).toEqual([])

        const name = `${route.path.replaceAll("/", "_").slice(0, 40)}-${viewport.width}.png`
        await page.screenshot({ path: info.outputPath(name), fullPage: true })
        await page.screenshot({ path: `test-results/shots/${name}`, fullPage: true })
      })
    }
  })
}

test.describe("teclado y comportamiento", () => {
  test.use({ viewport: { width: 1440, height: 900 } })

  test("el primer Tab llega a saltar al contenido, y este mueve el foco", async ({ page }) => {
    await gotoReady(page, "/dashboard", "Dashboard")
    await page.keyboard.press("Tab")
    const skip = page.getByRole("link", { name: "Saltar al contenido" })
    await expect(skip).toBeFocused()
    await expect(skip).toBeInViewport()
    await page.keyboard.press("Enter")
    await expect(page.locator("#main")).toBeFocused()
  })

  test("los controles interactivos tienen foco visible", async ({ page }) => {
    await gotoReady(page, "/playground", "Playground")
    const seed = page.getByLabel("Semilla")
    await seed.focus()
    const outline = await seed.evaluate((element) => getComputedStyle(element).outlineStyle)
    expect(outline).toBe("solid")
  })

  test("los objetivos táctiles principales miden al menos 44 px", async ({ page }) => {
    await gotoReady(page, "/playground", "Playground")
    for (const locator of [page.getByRole("button", { name: "Cerrar sesión" }), page.getByRole("link", { name: "Auditoría" })]) {
      const box = await locator.boundingBox()
      expect(box?.height ?? 0).toBeGreaterThanOrEqual(44)
    }
  })

  test("Escape cierra la confirmación, sin iniciar nada, y devuelve el foco", async ({ page }) => {
    const posts: string[] = []
    page.on("request", (request) => {
      if (request.method() === "POST" && request.url().includes("/demo-runs")) {
        posts.push(request.url())
      }
    })
    await gotoReady(page, "/playground", "Playground")
    await page.getByRole("radio", { name: /S04/ }).check()
    const launch = page.getByRole("button", { name: "Ejecutar comparación" })
    await launch.focus()
    await page.keyboard.press("Enter")
    await expect(page.getByRole("dialog")).toBeVisible()
    await page.keyboard.press("Escape")
    await expect(page.getByRole("dialog")).toBeHidden()
    await expect(launch).toBeFocused()
    expect(posts).toEqual([])
  })

  test("flujo con teclado: escenario, confirmación, comparación y recarga", async ({ page }) => {
    await gotoReady(page, "/playground", "Playground")
    await page.getByRole("radio", { name: /S04/ }).focus()
    await page.keyboard.press("Space")
    await page.getByRole("button", { name: "Ejecutar comparación" }).focus()
    await page.keyboard.press("Enter")
    await page.getByRole("button", { name: "Ejecutar con datos sintéticos" }).focus()
    await page.keyboard.press("Enter")
    await expect(page.getByRole("heading", { level: 1, name: "Comparación S04" })).toBeVisible()
    await expect(page.getByText("Completado")).toBeVisible({ timeout: 6000 })
    const protectedSide = page.getByRole("region", { name: /Con firewall/ })
    await expect(protectedSide.getByRole("row", { name: "Registros 8 8" })).toBeVisible()
    await expect(page.getByRole("region", { name: /Sin firewall/ }).getByRole("row", { name: "Registros 8 7" })).toBeVisible()
    await page.reload()
    await expect(page.getByRole("heading", { level: 1, name: "Comparación S04" })).toBeVisible()
  })

  test("los filtros de auditoría sobreviven a recargar y a ir atrás", async ({ page }) => {
    await gotoReady(page, "/audit", "Auditoría")
    await page.getByLabel("Decisión").selectOption("DENY")
    await page.getByRole("button", { name: "Aplicar filtros" }).click()
    await expect(page).toHaveURL(/decision=DENY/)
    await expect(page.getByRole("link", { name: "Abrir evento 4" })).toBeVisible()
    await page.reload()
    await expect(page.getByLabel("Decisión")).toHaveValue("DENY")
    await page.getByRole("link", { name: "Abrir evento 4" }).click()
    await expect(page.getByRole("heading", { level: 1, name: "Evento 4" })).toBeVisible()
    await page.goBack()
    await expect(page.getByLabel("Decisión")).toHaveValue("DENY")
  })

  test("la matriz deja siete escenarios sin ejecutar", async ({ page }) => {
    await gotoReady(page, "/matrix", "Matriz de ataques")
    await expect(page.getByText("No ejecutado")).toHaveCount(7)
  })

  test("cerrar sesión vuelve al acceso y no quedan datos en pantalla", async ({ page }) => {
    await gotoReady(page, "/agents", "Agentes")
    await page.getByRole("button", { name: "Cerrar sesión" }).click()
    await expect(page.getByLabel("Usuario")).toBeVisible()
    await expect(page.getByText("Agente de demostración")).toHaveCount(0)
  })

  test("nada se guarda en el almacenamiento del navegador", async ({ page }) => {
    await gotoReady(page, "/dashboard", "Dashboard")
    const stored = await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length }))
    expect(stored).toEqual({ local: 0, session: 0 })
  })
})

test.describe("móvil", () => {
  test.use({ viewport: { width: 360, height: 800 } })

  test("el menú se abre, navega y se cierra", async ({ page }) => {
    await gotoReady(page, "/dashboard", "Dashboard")
    const nav = page.getByRole("navigation", { name: "Principal" })
    await expect(nav).toBeHidden()
    const menu = page.getByRole("button", { name: "Menú" })
    await menu.click()
    await expect(menu).toHaveAttribute("aria-expanded", "true")
    await nav.getByRole("link", { name: "Auditoría" }).click()
    await expect(page.getByRole("heading", { level: 1, name: "Auditoría" })).toBeVisible()
    await expect(nav).toBeHidden()
  })
})
