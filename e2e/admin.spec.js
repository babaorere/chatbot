const { test, expect } = require("@playwright/test");
const { mockAdminApi } = require("./helpers/mock-api");

test.describe("admin frontend", () => {
  test("renders dashboard, creates tenant, updates agent config, and edits a setting", async ({ page }) => {
    const state = await mockAdminApi(page);

    await page.goto("/frontend/admin/index.html");

    await expect(page).toHaveTitle(/Admin Portal/);
    await expect(page.locator("#tenantCount")).toHaveText("2");
    await expect(page.locator("#activeTenantCount")).toHaveText("1");

    await page.getByRole("link", { name: /tenants/i }).click();
    await expect(page.locator("#pageTitle")).toContainText("Tenants");
    await expect(page.locator("#tenantsBody tr")).toHaveCount(2);

    await page.locator("#addTenantBtnTop").click();
    await page.locator("#tenantSlug").fill("licores-sur");
    await page.locator("#tenantName").fill("Licores del Sur");
    await page.locator("#tenantInstruction").fill("Asiste con ventas del tenant sur.");
    await page.locator("#tenantModel").fill("openrouter/test-model");
    await page.locator("#tenantApiKey").fill("secret-key");
    await page.getByRole("button", { name: /Crear Tenant/i }).click();

    await expect(page.locator("#toastContainer")).toContainText("Tenant creado");
    await expect(page.locator("#tenantCount")).toHaveText("3");
    await expect(page.locator("#tenantsBody tr")).toHaveCount(3);
    expect(state.tenants).toHaveLength(3);

    await page.getByRole("link", { name: /agente ia/i }).click();
    await page.locator("#agentTenant").selectOption("tenant-1");
    await expect(page.locator("#agentModel")).toHaveValue(state.agentConfig["tenant-1"].model);
    await page.locator("#agentInstruction").fill("Nueva instrucción operacional.");
    await page.getByRole("button", { name: /Guardar Configuración/i }).click();
    await expect(page.locator("#toastContainer")).toContainText("Configuración del agente actualizada");
    expect(state.agentConfig["tenant-1"].instruction).toBe("Nueva instrucción operacional.");

    await page.getByRole("link", { name: /configuración/i }).click();
    await page.getByRole("button", { name: /Editar/i }).first().click();
    await page.locator("#settingValue").fill("true");
    await page.getByRole("button", { name: /^Guardar$/i }).click();
    await expect(page.locator("#toastContainer")).toContainText("Setting actualizado");
  });
});
