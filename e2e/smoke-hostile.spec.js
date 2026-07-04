const { test, expect } = require("@playwright/test");
const { mockAdminApi, mockTenantApi } = require("./helpers/mock-api");

test.describe("smoke and hostile frontend paths", () => {
  test("admin tolerates backend failure on initial settings load without crashing the shell", async ({ page }) => {
    await page.addInitScript(() => {
      window.sessionStorage.setItem("admin_api_key", "mock-admin-api-key");
    });
    await page.route("http://localhost:8001/**", async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname === "/admin/settings") {
        return route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ error: "backend down" }),
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
    await expect(page.locator("#systemSettingsCount")).toHaveText("0");
  });

  test("tenant bootstrap works from prompt and category creation flow stays functional", async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.removeItem("tenant_id");
      window.prompt = () => "tenant-from-prompt";
      window.confirm = () => true;
    });
    const state = await mockTenantApi(page);

    await page.goto("/frontend/tenant/index.html");

    await expect(page.locator("#businessName")).toHaveText("Botilleria Centro");
    await expect(page.locator("#categoriesBody tr")).toHaveCount(2);

    await page.locator('.sidebar-nav .nav-link[data-section="categories"]').click();
    await page.locator("#addCategoryBtn").click();
    await page.locator("#catName").fill("Whiskies");
    await page.getByRole("button", { name: /Guardar grupo/i }).click();

    await expect(page.locator("#toastContainer")).toContainText("Grupo guardado");
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
    await page.locator('.sidebar-nav .nav-link[data-section="products"]').click();

    await page.locator("#exportProductsBtn").click();
    await expect(page.locator("#toastContainer")).toContainText("Catálogo descargado");

    await page.locator("#exportTemplateBtn").click();
    await expect(page.locator("#toastContainer")).toContainText("Plantilla descargada");

    await page.locator("#importProductsInput").setInputFiles({
      name: "productos.xlsx",
      mimeType:
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      buffer: Buffer.from("fake-xlsx"),
    });

    await expect(page.locator("#toastContainer")).toContainText("Carga completada");
  });

  test("shared smoke: both frontends render their main shell and navigation", async ({ page }) => {
    await page.addInitScript(() => {
      window.sessionStorage.setItem("admin_api_key", "mock-admin-api-key");
    });
    await mockAdminApi(page);
    await page.goto("/frontend/admin/index.html");
    await expect(page.locator(".sidebar-nav .nav-link")).toHaveCount(5);

    const other = await page.context().newPage();
    await other.addInitScript(() => {
      window.localStorage.setItem("tenant_id", "tenant-1");
    });
    await mockTenantApi(other);
    await other.goto("/frontend/tenant/index.html");
    await expect(other.locator(".sidebar-nav .nav-link")).toHaveCount(7);
    await other.close();
  });

  test("both frontends handle rate limiting 429 with user-friendly toast and logout confirmation", async ({ page }) => {
    await page.addInitScript(() => {
      window.sessionStorage.setItem("admin_api_key", "mock-admin-api-key");
      window.confirm = () => true;
    });
    await mockAdminApi(page);

    await page.route("http://localhost:8001/admin/settings", async (route) => {
      return route.fulfill({
        status: 429,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Too many requests" }),
      });
    });

    await page.goto("/frontend/admin/index.html");
    await expect(page.locator("#toastContainer")).toContainText("límite de solicitudes");

    await page.unroute("http://localhost:8001/admin/settings");
    await page.goto("/frontend/admin/index.html");
    await page.locator("#adminLogoutBtn").click();
    await expect(page.locator("#loginOverlay")).toBeVisible();
  });
});
