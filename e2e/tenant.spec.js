const { test, expect } = require("@playwright/test");
const { mockTenantApi } = require("./helpers/mock-api");

test.describe("tenant frontend", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("tenant_id", "tenant-1");
      window.URL.createObjectURL = () => "blob:mock";
      window.URL.revokeObjectURL = () => {};
      window.confirm = () => true;
    });
  });

  test("renders tenant dashboard, updates profile, creates product and kb entry", async ({ page }) => {
    const state = await mockTenantApi(page);

    await page.goto("/frontend/tenant/index.html");

    await expect(page).toHaveTitle(/Panel del negocio/);
    await expect(page.locator("#businessName")).toHaveText("Botilleria Centro");
    await expect(page.locator("#userCount")).toHaveText("42");
    await expect(page.locator("#convCount")).toHaveText("128");
    await expect(page.locator("#productCount")).toHaveText("1");
    await expect(page.locator("#kbCount")).toHaveText("1");
    await page.getByRole("link", { name: /datos del negocio/i }).click();
    await expect(page.locator("#profileHoursEditor .hours-row")).toHaveCount(7);
    await expect(page.locator("#profileHoursSummary")).toContainText("Lunes");
    await page.locator('[data-hours-preset="weekdays"]').click();
    await expect(page.locator("#hours-domingo-closed")).toBeChecked();

    await page.locator("#profileName").fill("Botilleria Centro Premium");
    await page.locator("#profileCity").fill("Las Condes");
    await page.locator("#hours-domingo-closed").check();
    await page.locator("#profileHumanAvailable").uncheck();
    await page.getByRole("button", { name: /Guardar cambios/i }).click();
    await expect(page.locator("#toastContainer")).toContainText("Datos del negocio actualizados");
    expect(state.profile.name).toBe("Botilleria Centro Premium");
    expect(state.profile.city).toBe("Las Condes");
    expect(state.profile.human_agent_available).toBe(false);
    expect(state.profile.business_hours.Domingo.closed).toBe(true);

    await page.locator('.nav-link[data-section="products"]').click();
    await page.getByRole("button", { name: /Agregar producto/i }).click();
    await page.locator("#prodName").fill("Whisky 12 años");
    await page.locator("#prodDesc").fill("Botella premium");
    await page.locator("#prodPrice").fill("21990");
    await page.locator("#prodStock").fill("8");
    await page.locator("#prodFormat").fill("750ml");
    await page.locator("#prodUnit").fill("un");
    await page.locator("#prodCategory").selectOption("Piscos");
    await page.getByRole("button", { name: /Guardar producto/i }).click();
    await expect(page.locator("#toastContainer")).toContainText("Producto guardado");
    await expect(page.locator("#productsBody tr")).toHaveCount(2);

    await page.locator('.nav-link[data-section="knowledge"]').click();
    await page.getByRole("button", { name: /Agregar respuesta/i }).click();
    await page.locator("#kbCategory").fill("Pagos");
    await page.locator("#kbTitle").fill("Formas de pago");
    await page.locator("#kbContent").fill("Aceptamos transferencia y efectivo.");
    await page.getByRole("button", { name: /Guardar respuesta/i }).click();
    await expect(page.locator("#toastContainer")).toContainText("Respuesta guardada");
    await expect(page.locator("#kbBody tr")).toHaveCount(2);

    await page.locator("#kbSearchInput").fill("horario");
    await page.getByRole("button", { name: /^Buscar$/i }).click();
    await expect(page.locator("#toastContainer")).toContainText("resultados encontrados");
  });

  test("Phase 2: table search filtering and bulk operations bar work as expected", async ({ page }) => {
    await mockTenantApi(page);
    await page.goto("/frontend/tenant/index.html");

    // Check Products real-time filter and bulk selection bar
    await page.locator('.nav-link[data-section="products"]').click();
    await expect(page.locator("#productsBody tr")).toHaveCount(1);
    await page.locator("#productsFilterInput").fill("Pisco");
    await expect(page.locator("#productsBody tr:visible")).toHaveCount(1);
    await page.locator("#productsFilterInput").fill("NoExisteProducto");
    await expect(page.locator("#productsBody tr:visible")).toHaveCount(0);
    await page.locator("#productsFilterInput").fill("");
    await expect(page.locator("#productsBody tr:visible")).toHaveCount(1);

    await page.locator("#selectAllProducts").check();
    await expect(page.locator("#productsBulkBar")).toBeVisible();
    await expect(page.locator("#productsBulkCount")).toContainText("1 sel.");
    await page.locator("#selectAllProducts").uncheck();
    await expect(page.locator("#productsBulkBar")).toBeHidden();
  });

  test("Phase 3: visual metrics charts and interactive AI agent simulator work as expected", async ({ page }) => {
    await mockTenantApi(page);
    await page.goto("/frontend/tenant/index.html");

    // Verify visual charts are rendered
    await expect(page.locator("#chartCategoryDistribution")).toContainText("Piscos");
    await expect(page.locator("#chartAvailability")).toContainText("Disponibles: 1 (100%)");
    await expect(page.locator("#chartKbCoverage")).toContainText("Respuestas Activas");

    // Test Interactive AI Agent Preview
    await page.locator('.nav-link[data-section="preview"]').click();
    await expect(page.locator("#previewAgentName")).toHaveText("Asistente Virtual del Negocio");
    await expect(page.locator("#previewMessages")).toContainText("¿En qué le puedo ayudar hoy?");

    await page.locator("#previewInput").fill("¿Tiene pisco?");
    await page.getByRole("button", { name: /^Enviar$/i }).click();
    await expect(page.locator("#previewMessages")).toContainText("Respuesta simulada del agente para: \"¿Tiene pisco?\"");

    await page.locator("#clearPreviewBtn").click();
    await expect(page.locator("#previewMessages")).not.toContainText("Respuesta simulada");
  });

  test("Phase 4: visual charts display empty fallback message when catalog or kb is empty", async ({ page }) => {
    const state = await mockTenantApi(page);
    state.products = [];
    state.kbEntries = [];

    await page.goto("/frontend/tenant/index.html");
    await expect(page.locator("#chartCategoryDistribution")).toContainText("No hay productos para graficar");
    await expect(page.locator("#chartAvailability")).toContainText("No hay productos para evaluar disponibilidad");
    await expect(page.locator("#chartKbCoverage")).toContainText("Aún no hay respuestas guardadas en la base de conocimiento");
  });
});
