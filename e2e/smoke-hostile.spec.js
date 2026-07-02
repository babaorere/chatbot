const { test, expect } = require("@playwright/test");
const { mockAdminApi, mockTenantApi } = require("./helpers/mock-api");

test.describe("smoke and hostile frontend paths", () => {
  test("admin tolerates backend failure on initial tenants load without crashing the shell", async ({ page }) => {
    await page.route("http://localhost:8001/**", async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname === "/admin/tenants") {
        return route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ error: "backend down" }),
        });
      }
      if (url.pathname === "/admin/settings") {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ maintenance_mode: false }),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    await page.goto("/frontend/admin/index.html");

    await expect(page.locator("h1")).toContainText("Admin");
    await expect(page.locator("#pageTitle")).toContainText("Dashboard");
    await expect(page.locator("#tenantCount")).toHaveText("0");
  });

  test("tenant bootstrap works from prompt and category creation flow stays functional", async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.removeItem("tenant_id");
      window.prompt = () => "tenant-from-prompt";
      window.confirm = () => true;
    });
    const state = await mockTenantApi(page);

    await page.goto("/frontend/tenant/index.html");

    await expect(page.locator("#tenantName")).toHaveText("Botilleria Centro");
    await expect(page.locator("#categoriesBody tr")).toHaveCount(2);

    await page.getByRole("link", { name: /categorías/i }).click();
    await page.getByRole("button", { name: /\+ Nueva Categoría/i }).click();
    await page.locator("#catName").fill("Whiskies");
    await page.getByRole("button", { name: /^Guardar$/i }).click();

    await expect(page.locator("#toastContainer")).toContainText("Categoría guardada");
    expect(state.categories.some((item) => item.name === "Whiskies")).toBeTruthy();
  });

  test("tenant export and import controls issue requests without blocking the UI", async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("tenant_id", "tenant-1");
      window.URL.createObjectURL = () => "blob:mock";
      window.URL.revokeObjectURL = () => {};
      window.confirm = () => true;
    });
    await mockTenantApi(page);

    await page.goto("/frontend/tenant/index.html");
    await page.getByRole("link", { name: /productos/i }).click();

    await page.locator("#exportProductsBtn").click();
    await expect(page.locator("#toastContainer")).toContainText("Exportación completada");

    await page.locator("#exportTemplateBtn").click();
    await expect(page.locator("#toastContainer")).toContainText("Plantilla descargada");

    await page.locator("#importProductsInput").setInputFiles({
      name: "productos.xlsx",
      mimeType:
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      buffer: Buffer.from("fake-xlsx"),
    });

    await expect(page.locator("#toastContainer")).toContainText("Importación completada");
  });

  test("shared smoke: both frontends render their main shell and navigation", async ({ page }) => {
    await mockAdminApi(page);
    await page.goto("/frontend/admin/index.html");
    await expect(page.locator(".sidebar-nav .nav-link")).toHaveCount(4);

    const other = await page.context().newPage();
    await other.addInitScript(() => {
      window.localStorage.setItem("tenant_id", "tenant-1");
    });
    await mockTenantApi(other);
    await other.goto("/frontend/tenant/index.html");
    await expect(other.locator(".sidebar-nav .nav-link")).toHaveCount(6);
    await other.close();
  });
});
