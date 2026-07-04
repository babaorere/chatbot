const { test, expect } = require("@playwright/test");
const { mockAdminApi } = require("./helpers/mock-api");

test.describe("admin frontend", () => {
  test("renders dashboard, updates agent config, edits a setting, manages tenant access, and manages admins", async ({ page }) => {
    await page.addInitScript(() => {
      window.sessionStorage.setItem("admin_api_key", "mock-admin-api-key");
      window.confirm = () => true;
    });
    const state = await mockAdminApi(page);

    await page.goto("/frontend/admin/index.html");

    // Title / shell validation
    await expect(page).toHaveTitle(/Admin Portal/);
    await expect(page.locator("#activeAgentStatus")).toBeVisible();
    await expect(page.locator("#systemSettingsCount")).toContainText("2");

    // 1. Agente IA Configuration Section
    await page.getByRole("link", { name: /agente ia/i }).click();
    await page.locator("#agentInstruction").fill("Nueva instrucción operacional global.");
    await page.getByRole("button", { name: /Guardar Configuración/i }).click();
    await expect(page.locator("#toastContainer")).toContainText("Configuración del Agente guardada con éxito");

    // 2. Settings Section
    await page.getByRole("link", { name: /configuración/i }).click();
    await page.getByRole("button", { name: /Editar/i }).first().click();
    await page.locator("#settingValue").fill("true");
    await page.getByRole("button", { name: /^Guardar$/i }).click();
    await expect(page.locator("#toastContainer")).toContainText("Setting actualizado");

    // 3. Tenant Access Section
    await page.getByRole("link", { name: /acceso tenant/i }).click();
    await expect(page.locator("#tenantUsersBody tr")).toHaveCount(1);
    await page.getByRole("button", { name: /Desactivar/i }).click();
    await expect(page.locator("#toastContainer")).toContainText("Usuario desactivado");

    // 4. System Admins & Alerts Section
    await page.getByRole("link", { name: /administradores/i }).click();
    await page.locator("#addAdminBtn").click();
    await page.locator("#adminName").fill("Admin de Alertas");
    await page.locator("#adminEmail").fill("alertas@chatbot.cl");
    await page.locator("#adminTelegramChatId").fill("987654321");
    await page.locator("#adminAlertLatency").check();
    await page.locator("#adminAlertError").check();
    await page.getByRole("button", { name: /Crear Administrador/i }).click();
    await expect(page.locator("#toastContainer")).toContainText("Administrador creado");
  });
});
